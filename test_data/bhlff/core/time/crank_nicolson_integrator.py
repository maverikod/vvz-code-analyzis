"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Crank-Nicolson integrator for 7D phase field dynamics.

This module implements the Crank-Nicolson integrator for solving dynamic
phase field equations in 7D space-time with second-order accuracy and
unconditional stability.

Physical Meaning:
    Crank-Nicolson integrator provides second-order accurate solution
    for dynamic phase field equations with unconditional stability,
    making it suitable for stiff problems and long-time integration.

Mathematical Foundation:
    Implements the Crank-Nicolson scheme:
    (a^{n+1} - a^n)/dt + (1/2)[L(a^{n+1}) + L(a^n)] = (1/2)[s^{n+1} + s^n]
    where L is the fractional Laplacian operator.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import logging

from .base_integrator import BaseTimeIntegrator
from .memory_kernel import MemoryKernel
from bhlff.core.bvp.quench_detector import QuenchDetector
from ..fft.unified_spectral_operations import UnifiedSpectralOperations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..fft import FractionalLaplacian


class CrankNicolsonIntegrator(BaseTimeIntegrator):
    """
    Crank-Nicolson integrator for 7D phase field dynamics.

    Physical Meaning:
        Provides second-order accurate solution for dynamic phase field
        equations with unconditional stability, making it suitable for
        stiff problems and long-time integration in 7D space-time.

    Mathematical Foundation:
        Implements the Crank-Nicolson scheme:
        (a^{n+1} - a^n)/dt + (1/2)[L(a^{n+1}) + L(a^n)] = (1/2)[s^{n+1} + s^n]
        where L is the fractional Laplacian operator.

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _spectral_ops (SpectralOperations): Spectral operations for FFT.
        _fractional_laplacian (FractionalLaplacian): Fractional Laplacian operator.
        _spectral_coeffs (np.ndarray): Pre-computed spectral coefficients.
        _memory_kernel (Optional[MemoryKernel]): Memory kernel for non-local effects.
        _quench_detector (Optional[QuenchDetector]): Quench detection system.
    """

    def __init__(self, domain, parameters) -> None:
        """
        Initialize Crank-Nicolson integrator.

        Physical Meaning:
            Sets up the Crank-Nicolson integrator with the computational domain
            and physics parameters, pre-computing spectral coefficients
            for efficient integration.

        Args:
            domain (Domain): Computational domain for the simulation.
            parameters (Parameters): Physics parameters controlling
                the behavior of the phase field system.
        """
        super().__init__(domain, parameters)

        # Initialize unified spectral operations (CUDA-aware, blocked)
        self._spectral_ops = UnifiedSpectralOperations(domain, parameters.precision)

        # Initialize fractional Laplacian
        from ..fft import FractionalLaplacian

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

        self._initialized = True
        self.logger.info("Crank-Nicolson integrator initialized")

    def _setup_spectral_coefficients(self) -> None:
        """
        Setup spectral coefficients for Crank-Nicolson integrator.

        Physical Meaning:
            Pre-computes the spectral representation of the operator
            for efficient Crank-Nicolson integration.
        """
        # Get spectral coefficients from fractional Laplacian
        self._spectral_coeffs = self._fractional_laplacian.get_spectral_coefficients()

        # Scale by diffusion coefficient
        self._spectral_coeffs *= self.parameters.nu

        self.logger.info("Spectral coefficients computed for Crank-Nicolson")

    def integrate(
        self,
        initial_field: np.ndarray,
        source_field: np.ndarray,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate the dynamic equation over time using Crank-Nicolson method.

        Physical Meaning:
            Solves the dynamic phase field equation over the specified
            time steps using the Crank-Nicolson scheme, providing
            second-order accuracy with unconditional stability.

        Mathematical Foundation:
            For each time step, applies the Crank-Nicolson scheme:
            (a^{n+1} - a^n)/dt + (1/2)[L(a^{n+1}) + L(a^n)] = (1/2)[s^{n+1} + s^n]

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
        # Ensure initial on correct dtype (avoid extra copies later)
        if initial_field.dtype != self._complex_dtype:
            initial_field = initial_field.astype(self._complex_dtype, copy=False)
        result[0] = initial_field

        # Current field state (no extra copy if already new array)
        current_field = result[0]

        # Integrate over time steps
        for i in range(1, len(time_steps)):
            dt = time_steps[i] - time_steps[i - 1]
            current_source = source_field[i - 1]
            next_source = source_field[i]

            # Perform single step
            current_field = self.step(current_field, current_source, next_source, dt)
            result[i] = current_field.copy()

            # Check for quench events
            if self._check_quench(current_field, time_steps[i]):
                self.logger.warning(f"Quench detected at t={time_steps[i]:.3f}")
                # Could implement special handling here

        self.logger.info(
            f"Crank-Nicolson integration completed over {len(time_steps)} time steps"
        )
        return result

    def step(
        self,
        current_field: np.ndarray,
        current_source: np.ndarray,
        next_source: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        """
        Perform a single time step using Crank-Nicolson method.

        Physical Meaning:
            Advances the field configuration by one time step using the
            Crank-Nicolson scheme, providing second-order accuracy
            with unconditional stability.

        Mathematical Foundation:
            Applies the Crank-Nicolson scheme:
            (a^{n+1} - a^n)/dt + (1/2)[L(a^{n+1}) + L(a^n)] = (1/2)[s^{n+1} + s^n]
            Solved in spectral space for efficiency.

        Args:
            current_field (np.ndarray): Current field configuration.
            current_source (np.ndarray): Source term at current time.
            next_source (np.ndarray): Source term at next time.
            dt (float): Time step size.

        Returns:
            np.ndarray: Field configuration at next time step.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        if dt <= 0:
            raise ValueError("Time step must be positive")

        if current_field.shape != self.domain.shape:
            raise ValueError("Field shape must match domain")
        if not np.iscomplexobj(current_field):
            raise ValueError("Field must be complex")
        if (
            current_source.shape != self.domain.shape
            or next_source.shape != self.domain.shape
        ):
            raise ValueError("Source shape must match domain")

        # Transform to spectral space
        current_spectral = self._spectral_ops.forward_fft(current_field, "ortho")
        current_source_spectral = self._spectral_ops.forward_fft(
            current_source, "ortho"
        )
        next_source_spectral = self._spectral_ops.forward_fft(next_source, "ortho")

        # Apply memory kernel effects if present
        if self._memory_kernel is not None:
            memory_contribution = self._memory_kernel.get_memory_contribution()
            memory_spectral = self._spectral_ops.forward_fft(
                memory_contribution, "ortho"
            )
            current_source_spectral += memory_spectral

        # Crank-Nicolson scheme in spectral space
        # (a^{n+1} - a^n)/dt + (1/2)[L(a^{n+1}) + L(a^n)] = (1/2)[s^{n+1} + s^n]
        # Rearranged: a^{n+1} = [a^n - (dt/2)L(a^n) + (dt/2)(s^{n+1} + s^n)] / [1 + (dt/2)L]

        # Current field contribution
        current_contribution = (
            current_spectral - (dt / 2) * self._spectral_coeffs * current_spectral
        )

        # Source contribution
        source_contribution = (dt / 2) * (
            current_source_spectral + next_source_spectral
        )

        # Solve for next field
        denominator = 1 + (dt / 2) * self._spectral_coeffs
        next_spectral = (current_contribution + source_contribution) / denominator

        # Transform back to real space
        next_field = self._spectral_ops.inverse_fft(next_spectral, "ortho").astype(
            self._complex_dtype
        )

        # Evolve memory kernel if present
        if self._memory_kernel is not None:
            self._memory_kernel.evolve(current_field, dt)

        return next_field

    def step_implicit(
        self, current_field: np.ndarray, source_field: np.ndarray, dt: float
    ) -> np.ndarray:
        """
        Perform a single time step using implicit Crank-Nicolson method.

        Physical Meaning:
            Advances the field configuration by one time step using the
            implicit Crank-Nicolson scheme, providing unconditional stability
            for stiff problems.

        Mathematical Foundation:
            Implicit scheme: (a^{n+1} - a^n)/dt + L(a^{n+1}) = s^{n+1}
            Solved as: a^{n+1} = [a^n + dt*s^{n+1}] / [1 + dt*L]

        Args:
            current_field (np.ndarray): Current field configuration.
            source_field (np.ndarray): Source term at next time.
            dt (float): Time step size.

        Returns:
            np.ndarray: Field configuration at next time step.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        if dt <= 0:
            raise ValueError("Time step must be positive")

        if current_field.shape != self.domain.shape:
            raise ValueError("Field shape must match domain")
        if not np.iscomplexobj(current_field):
            raise ValueError("Field must be complex")
        if source_field.shape != self.domain.shape:
            raise ValueError("Source shape must match domain")

        # Transform to spectral space
        current_spectral = self._spectral_ops.forward_fft(current_field, "ortho")
        source_spectral = self._spectral_ops.forward_fft(source_field, "ortho")

        # Apply memory kernel effects if present
        if self._memory_kernel is not None:
            memory_contribution = self._memory_kernel.get_memory_contribution()
            memory_spectral = self._spectral_ops.forward_fft(
                memory_contribution, "ortho"
            )
            source_spectral += memory_spectral

        # Implicit scheme in spectral space
        # a^{n+1} = [a^n + dt*s^{n+1}] / [1 + dt*L]
        numerator = current_spectral + dt * source_spectral
        denominator = 1 + dt * self._spectral_coeffs

        next_spectral = numerator / denominator

        # Transform back to real space
        next_field = self._spectral_ops.inverse_fft(next_spectral, "ortho").astype(
            self._complex_dtype
        )

        # Evolve memory kernel if present
        if self._memory_kernel is not None:
            self._memory_kernel.evolve(current_field, dt)

        return next_field

    def __repr__(self) -> str:
        """String representation of integrator."""
        return (
            f"CrankNicolsonIntegrator("
            f"domain={self.domain.shape}, "
            f"nu={self.parameters.nu}, "
            f"beta={self.parameters.beta}, "
            f"lambda={self.parameters.lambda_param})"
        )
