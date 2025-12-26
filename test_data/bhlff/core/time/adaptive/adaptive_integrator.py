"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Adaptive integrator for 7D phase field dynamics.

This module implements the adaptive integrator for solving dynamic phase field
equations in 7D space-time with automatic error control and time step adjustment.

Physical Meaning:
    Adaptive integrator provides automatic time step control to maintain
    accuracy while ensuring numerical stability of phase field evolution
    in 7D space-time with optimal performance.

Mathematical Foundation:
    Uses embedded Runge-Kutta methods with error estimation and automatic
    step size adjustment for optimal performance and accuracy control.
"""

from typing import Dict, Any, Optional, Tuple, Callable
import numpy as np
import logging

from ..base_integrator import BaseTimeIntegrator
from ..memory_kernel import MemoryKernel
from bhlff.core.bvp.quench_detector import QuenchDetector
from ...fft.unified_spectral_operations import UnifiedSpectralOperations
from .error_estimation import ErrorEstimation
from .runge_kutta import RungeKuttaMethods
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...fft import FractionalLaplacian


class AdaptiveIntegrator(BaseTimeIntegrator):
    """
    Adaptive integrator with error control and stability monitoring.

    Physical Meaning:
        Automatically adjusts time step to maintain accuracy while
        ensuring numerical stability of phase field evolution in 7D space-time.
        Uses embedded Runge-Kutta methods with error estimation.

    Mathematical Foundation:
        Implements adaptive time stepping with:
        - Error estimation using embedded methods
        - Automatic step size adjustment
        - Stability monitoring and CFL conditions
        - Performance optimization through step size control

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _spectral_ops (SpectralOperations): Spectral operations for FFT.
        _fractional_laplacian (FractionalLaplacian): Fractional Laplacian operator.
        _spectral_coeffs (np.ndarray): Pre-computed spectral coefficients.
        _memory_kernel (Optional[MemoryKernel]): Memory kernel for non-local effects.
        _quench_detector (Optional[QuenchDetector]): Quench detection system.
        _current_dt (float): Current time step.
        _min_dt (float): Minimum allowed time step.
        _max_dt (float): Maximum allowed time step.
        _tolerance (float): Error tolerance for adaptive control.
        _safety_factor (float): Safety factor for step size adjustment.
    """

    def __init__(
        self,
        domain,
        parameters,
        tolerance: float = 1e-8,
        safety_factor: float = 0.9,
        min_dt: float = 1e-6,
        max_dt: float = 1e-2,
    ) -> None:
        """
        Initialize adaptive integrator.

        Physical Meaning:
            Sets up the adaptive integrator with the computational domain
            and physics parameters, configuring error control and time step
            management for optimal performance.

        Args:
            domain (Domain): Computational domain for the simulation.
            parameters (Parameters): Physics parameters controlling
                the behavior of the phase field system.
            tolerance (float): Error tolerance for adaptive control.
            safety_factor (float): Safety factor for step size adjustment.
            min_dt (float): Minimum allowed time step.
            max_dt (float): Maximum allowed time step.
        """
        super().__init__(domain, parameters)

        # Initialize unified spectral operations (CUDA-aware, blocked)
        self._spectral_ops = UnifiedSpectralOperations(domain, parameters.precision)

        # Initialize fractional Laplacian
        from ...fft import FractionalLaplacian

        self._fractional_laplacian = FractionalLaplacian(
            domain, parameters.beta, parameters.lambda_param
        )

        # Pre-compute spectral coefficients
        self._spectral_coeffs = None
        self._setup_spectral_coefficients()

        # Select complex dtype based on precision
        self._complex_dtype = (
            np.complex64
            if str(self.parameters.precision).lower() in ("float32", "single")
            else np.complex128
        )

        # Initialize specialized components
        self._error_estimator = ErrorEstimation(tolerance, safety_factor)
        self._rk_methods = RungeKuttaMethods()

        # Adaptive control parameters
        self._tolerance = tolerance
        self._safety_factor = safety_factor
        self._min_dt = min_dt
        self._max_dt = max_dt
        self._current_dt = min_dt

        self._initialized = True
        self.logger.info(f"Adaptive integrator initialized with tolerance={tolerance}")

    def _setup_spectral_coefficients(self) -> None:
        """
        Setup spectral coefficients for adaptive integrator.

        Physical Meaning:
            Pre-computes the spectral representation of the operator
            for efficient adaptive integration with error estimation.
        """
        # Get spectral coefficients from fractional Laplacian
        self._spectral_coeffs = self._fractional_laplacian.get_spectral_coefficients()

        # Scale by diffusion coefficient
        self._spectral_coeffs *= self.parameters.nu

        self.logger.info("Spectral coefficients computed for adaptive integrator")

    def integrate(
        self,
        initial_field: np.ndarray,
        source_field: np.ndarray,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate the dynamic equation over time using adaptive method.

        Physical Meaning:
            Solves the dynamic phase field equation over the specified
            time steps using adaptive time stepping with automatic error
            control and step size adjustment.

        Mathematical Foundation:
            Uses embedded Runge-Kutta methods with error estimation:
            - Fourth-order accurate solution
            - Fifth-order error estimation
            - Automatic step size adjustment based on error
            - Stability monitoring and CFL conditions

        Args:
            initial_field (np.ndarray): Initial field configuration a(x,φ,0).
            source_field (np.ndarray): Source term s(x,φ,t) over time.
            time_steps (np.ndarray): Time points for integration.

        Returns:
            np.ndarray: Field evolution a(x,φ,t) over time.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        # Validate inputs
        if initial_field.shape != self.domain.shape:
            raise ValueError(
                f"Initial field shape {initial_field.shape} incompatible with domain {self.domain.shape}"
            )

        if source_field.shape != (len(time_steps),) + self.domain.shape:
            raise ValueError(
                f"Source field shape {source_field.shape} incompatible with time steps and domain"
            )

        # Initialize result array
        result = np.empty(
            (len(time_steps),) + self.domain.shape, dtype=self._complex_dtype
        )
        # Ensure initial on correct dtype
        if initial_field.dtype != self._complex_dtype:
            initial_field = initial_field.astype(self._complex_dtype, copy=False)
        result[0] = initial_field

        # Current field state
        current_field = result[0]
        current_time = time_steps[0]

        # Adaptive integration
        for i in range(1, len(time_steps)):
            target_time = time_steps[i]

            # Integrate from current_time to target_time with adaptive stepping
            current_field = self._adaptive_step_to_time(
                current_field, current_time, target_time, source_field, i
            )

            result[i] = current_field.copy()
            current_time = target_time

        return result

    def step(
        self, current_field: np.ndarray, source_field: np.ndarray, dt: float
    ) -> np.ndarray:
        """
        Perform a single adaptive time step.

        Physical Meaning:
            Advances the field configuration by one time step using
            adaptive error control and step size adjustment.

        Args:
            current_field (np.ndarray): Current field configuration.
            source_field (np.ndarray): Source term at current time.
            dt (float): Proposed time step size.

        Returns:
            np.ndarray: Field configuration at next time step.
        """
        # Use embedded Runge-Kutta method for error estimation
        field_next, error_estimate = self._rk_methods.embedded_rk_step(
            current_field, source_field, dt, self._compute_rhs
        )

        # Adjust time step based on error estimate
        self._adjust_time_step(error_estimate, dt)

        return field_next

    def _adaptive_step_to_time(
        self,
        current_field: np.ndarray,
        current_time: float,
        target_time: float,
        source_field: np.ndarray,
        time_index: int,
    ) -> np.ndarray:
        """
        Adaptively step from current_time to target_time.

        Physical Meaning:
            Performs adaptive integration from current time to target time,
            automatically adjusting step size to maintain accuracy.
        """
        field = current_field.copy()
        time = current_time

        while time < target_time:
            # Calculate remaining time
            remaining_time = target_time - time

            # Use current adaptive time step or remaining time, whichever is smaller
            dt = min(self._current_dt, remaining_time)

            # Get source at current time (interpolate if necessary)
            if time_index < len(source_field) - 1:
                # Linear interpolation between time points
                alpha = (time - time_index) / (time_index + 1 - time_index)
                source = (1 - alpha) * source_field[time_index] + alpha * source_field[
                    time_index + 1
                ]
            else:
                source = source_field[time_index]

            # Perform adaptive step
            field = self.step(field, source, dt)
            time += dt

            # Check if we've reached the target time
            if abs(time - target_time) < 1e-12:
                break

        return field

    def _compute_rhs(self, field: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute right-hand side of the dynamic equation.

        Physical Meaning:
            Computes the right-hand side of the dynamic phase field equation:
            RHS = -ν(-Δ)^β a - λa + s(x,φ,t)
        """
        # Transform to spectral space (CUDA-aware, blocked)
        field_spectral = self._spectral_ops.forward_fft(field, "ortho")

        # Apply spectral operator: -ν|k|^(2β) - λ
        rhs_spectral = -self._spectral_coeffs * field_spectral

        # Add source term
        source_spectral = self._spectral_ops.forward_fft(source, "ortho")
        rhs_spectral += source_spectral

        # Transform back to real space
        rhs = self._spectral_ops.inverse_fft(rhs_spectral, "ortho")

        # Ensure dtype
        if rhs.dtype != self._complex_dtype:
            rhs = rhs.astype(self._complex_dtype, copy=False)

        return rhs

    def _adjust_time_step(self, error_estimate: float, current_dt: float) -> None:
        """
        Adjust time step based on full error analysis.

        Physical Meaning:
            Automatically adjusts the time step based on comprehensive error
            estimation including Richardson extrapolation, stability analysis,
            and truncation error to maintain accuracy while optimizing performance.
        """
        if error_estimate > 0:
            # Calculate optimal time step based on error
            # For RK4(5), error scales as h^5, so optimal step size is:
            optimal_dt = current_dt * (self._tolerance / error_estimate) ** (1.0 / 5.0)

            # Apply safety factor for conservative step size
            optimal_dt *= self._safety_factor

            # Apply additional stability constraints
            optimal_dt = self._apply_stability_constraints(optimal_dt, error_estimate)

            # Clamp to allowed range
            self._current_dt = np.clip(optimal_dt, self._min_dt, self._max_dt)

            # Log step size adjustment
            if (
                abs(self._current_dt - current_dt) / current_dt > 0.1
            ):  # Significant change
                self.logger.debug(
                    f"Time step adjusted: {current_dt:.2e} -> {self._current_dt:.2e}, error: {error_estimate:.2e}"
                )
        else:
            # If no error, increase step size conservatively
            self._current_dt = min(self._current_dt * 1.1, self._max_dt)

    def _apply_stability_constraints(
        self, proposed_dt: float, error_estimate: float
    ) -> float:
        """
        Apply stability constraints to proposed time step.

        Physical Meaning:
            Applies stability constraints including CFL conditions
            and spectral stability requirements to ensure numerical stability.
        """
        # Delegate to adaptive stability helper to keep this file concise
        from .stability import apply_stability_constraints

        return apply_stability_constraints(
            proposed_dt=proposed_dt,
            error_estimate=error_estimate,
            tolerance=self._tolerance,
            domain=self.domain,
            parameters=self.parameters,
        )

    def get_current_time_step(self) -> float:
        """Get current adaptive time step."""
        return self._current_dt

    def set_tolerance(self, tolerance: float) -> None:
        """Set error tolerance for adaptive control."""
        self._tolerance = tolerance
        self.logger.info(f"Adaptive tolerance set to {tolerance}")

    def set_time_step_bounds(self, min_dt: float, max_dt: float) -> None:
        """Set time step bounds."""
        self._min_dt = min_dt
        self._max_dt = max_dt
        self._current_dt = np.clip(self._current_dt, min_dt, max_dt)
        self.logger.info(f"Time step bounds set to [{min_dt}, {max_dt}]")

    def get_integrator_info(self) -> Dict[str, Any]:
        """Get information about the integrator."""
        return {
            "type": "adaptive",
            "tolerance": self._tolerance,
            "safety_factor": self._safety_factor,
            "min_dt": self._min_dt,
            "max_dt": self._max_dt,
            "current_dt": self._current_dt,
            "initialized": self._initialized,
        }
