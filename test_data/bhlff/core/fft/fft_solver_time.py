"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Time-dependent methods for 7D FFT Solver.

This module provides time-dependent solving methods for the 7D phase field theory,
including temporal integrators, memory kernels, and quench detection.

Physical Meaning:
    Implements time-dependent solving methods for the dynamic phase field equation:
    ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
    using high-precision temporal integrators with support for memory kernels
    and quench detection.

Mathematical Foundation:
    Uses either exponential integrator (exact for harmonic sources) or
    Crank-Nicolson integrator (second-order accurate, unconditionally stable).

Example:
    >>> solver = FFTSolver7D(domain, parameters)
    >>> result = solver.solve_time_dependent(initial_field, source_field, time_steps)
"""

import numpy as np
from typing import Dict, Any, Optional, List
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import Domain
    from ..domain.parameters import Parameters
    from ..time import (
        BVPEnvelopeIntegrator,
        CrankNicolsonIntegrator,
        MemoryKernel,
        QuenchDetector,
    )


class FFTSolverTimeMethods:
    """
    Time-dependent methods for 7D FFT Solver.

    Physical Meaning:
        Implements time-dependent solving methods for the dynamic phase field equation:
        ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
        using high-precision temporal integrators with support for memory kernels
        and quench detection.

    Mathematical Foundation:
        Uses either exponential integrator (exact for harmonic sources) or
        Crank-Nicolson integrator (second-order accurate, unconditionally stable).

    Attributes:
        domain (Domain): Computational domain for the simulation.
        parameters (Parameters): Solver parameters.
        _envelope_integrator (BVPEnvelopeIntegrator): BVP envelope integrator.
        _crank_nicolson_integrator (CrankNicolsonIntegrator): Crank-Nicolson integrator.
        _memory_kernel (MemoryKernel): Memory kernel for non-local effects.
        _quench_detector (QuenchDetector): Quench detection system.
    """

    def __init__(self, domain: "Domain", parameters: "Parameters"):
        """
        Initialize time-dependent methods.

        Physical Meaning:
            Sets up the time-dependent methods with the computational domain
            and solver parameters, initializing temporal integrators and
            supporting components.

        Args:
            domain (Domain): Computational domain with grid information.
            parameters (Parameters): Solver parameters.
        """
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize time integrators
        self._envelope_integrator = None
        self._crank_nicolson_integrator = None
        self._memory_kernel = None
        self._quench_detector = None

        self.logger.info(f"FFTSolverTimeMethods initialized for domain {domain.shape}")

    def solve_time_dependent(
        self,
        initial_field: np.ndarray,
        source_field: np.ndarray,
        time_steps: np.ndarray,
        method: str = "envelope",
    ) -> np.ndarray:
        """
        Solve time-dependent problem using temporal integrators.

        Physical Meaning:
            Solves the dynamic phase field equation:
            ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
            using high-precision temporal integrators with support for
            memory kernels and quench detection.

        Mathematical Foundation:
            Uses either BVP envelope integrator (envelope modulation approach)
            or Crank-Nicolson integrator (second-order accurate, unconditionally stable).

        Args:
            initial_field (np.ndarray): Initial field configuration a(x,φ,0).
            source_field (np.ndarray): Source term s(x,φ,t) over time.
            time_steps (np.ndarray): Time points for integration.
            method (str): Integration method ('envelope' or 'crank_nicolson').

        Returns:
            np.ndarray: Field evolution a(x,φ,t) over time.
        """
        # Validate inputs
        if initial_field.shape != self.domain.shape:
            raise ValueError(
                f"Initial field shape {initial_field.shape} incompatible with domain {self.domain.shape}"
            )

        if source_field.shape != (len(time_steps),) + self.domain.shape:
            raise ValueError(
                f"Source field shape {source_field.shape} incompatible with time steps and domain"
            )

        # Get or create integrator
        if method == "envelope":
            if self._envelope_integrator is None:
                from ..time import BVPEnvelopeIntegrator

                self._envelope_integrator = BVPEnvelopeIntegrator(
                    self.domain, self.parameters
                )
                self._setup_integrator_components(self._envelope_integrator)
            integrator = self._envelope_integrator
        elif method == "crank_nicolson":
            if self._crank_nicolson_integrator is None:
                from ..time import CrankNicolsonIntegrator

                self._crank_nicolson_integrator = CrankNicolsonIntegrator(
                    self.domain, self.parameters
                )
                self._setup_integrator_components(self._crank_nicolson_integrator)
            integrator = self._crank_nicolson_integrator
        else:
            raise ValueError(f"Unknown integration method: {method}")

        # Integrate
        result = integrator.integrate(initial_field, source_field, time_steps)

        self.logger.info(f"Time-dependent integration completed using {method} method")
        return result

    def _setup_integrator_components(self, integrator) -> None:
        """
        Setup memory kernel and quench detector for integrator.

        Physical Meaning:
            Configures the integrator with memory kernel for non-local
            temporal effects and quench detector for monitoring energy
            dumping events.
        """
        # Setup memory kernel
        if self._memory_kernel is None:
            from ..time import MemoryKernel

            self._memory_kernel = MemoryKernel(self.domain, num_memory_vars=3)
        integrator.set_memory_kernel(self._memory_kernel)

        # Setup quench detector
        if self._quench_detector is None:
            from ..bvp.quench_detector import QuenchDetector
            from ..domain.domain_7d import Domain7D
            from ..domain.config import SpatialConfig, PhaseConfig, TemporalConfig

            # Create domain_7d from domain
            spatial_config = SpatialConfig(
                L_x=1.0, L_y=1.0, L_z=1.0, N_x=64, N_y=64, N_z=64
            )
            phase_config = PhaseConfig(N_phi_1=32, N_phi_2=32, N_phi_3=32)
            temporal_config = TemporalConfig(T_max=1.0, N_t=100, dt=0.01)
            domain_7d = Domain7D(spatial_config, phase_config, temporal_config)

            config = {"use_cuda": False}
            self._quench_detector = QuenchDetector(domain_7d, config)
        integrator.set_quench_detector(self._quench_detector)

    def set_memory_kernel(
        self,
        num_memory_vars: int = 3,
        relaxation_times: Optional[List[float]] = None,
        coupling_strengths: Optional[List[float]] = None,
    ) -> None:
        """
        Configure memory kernel for non-local temporal effects.

        Physical Meaning:
            Sets up the memory kernel with specified number of memory
            variables, relaxation times, and coupling strengths for
            non-local temporal effects in phase field evolution.

        Args:
            num_memory_vars (int): Number of memory variables.
            relaxation_times (Optional[List[float]]): Relaxation times τⱼ.
            coupling_strengths (Optional[List[float]]): Coupling strengths γⱼ.
        """
        from ..time import MemoryKernel

        self._memory_kernel = MemoryKernel(self.domain, num_memory_vars)

        if relaxation_times is not None:
            self._memory_kernel.set_relaxation_times(relaxation_times)

        if coupling_strengths is not None:
            self._memory_kernel.set_coupling_strengths(coupling_strengths)

        # Update existing integrators
        if self._envelope_integrator is not None:
            self._envelope_integrator.set_memory_kernel(self._memory_kernel)
        if self._crank_nicolson_integrator is not None:
            self._crank_nicolson_integrator.set_memory_kernel(self._memory_kernel)

        self.logger.info(f"Memory kernel configured with {num_memory_vars} variables")

    def set_quench_detector(
        self,
        energy_threshold: float = 1e-3,
        rate_threshold: float = 1e-2,
        magnitude_threshold: float = 10.0,
    ) -> None:
        """
        Configure quench detection system.

        Physical Meaning:
            Sets up the quench detection system with specified thresholds
            for monitoring energy dumping events during integration.

        Args:
            energy_threshold (float): Energy change threshold for quench detection.
            rate_threshold (float): Rate of change threshold.
            magnitude_threshold (float): Field magnitude threshold.
        """
        from ..bvp.quench_detector import QuenchDetector

        # Create config for new QuenchDetector
        config = {
            "amplitude_threshold": magnitude_threshold,
            "detuning_threshold": rate_threshold,
            "gradient_threshold": energy_threshold,
            "use_cuda": False,
        }

        # Create domain_7d from domain
        from ..domain.domain_7d import Domain7D
        from ..domain.config import SpatialConfig, PhaseConfig, TemporalConfig

        # Convert domain to domain_7d
        spatial_config = SpatialConfig(
            L_x=1.0, L_y=1.0, L_z=1.0, N_x=64, N_y=64, N_z=64
        )
        phase_config = PhaseConfig(N_phi_1=32, N_phi_2=32, N_phi_3=32)
        temporal_config = TemporalConfig(T_max=1.0, N_t=100, dt=0.01)
        domain_7d = Domain7D(spatial_config, phase_config, temporal_config)

        self._quench_detector = QuenchDetector(domain_7d, config)

        # Update existing integrators
        if self._envelope_integrator is not None:
            self._envelope_integrator.set_quench_detector(self._quench_detector)
        if self._crank_nicolson_integrator is not None:
            self._crank_nicolson_integrator.set_quench_detector(self._quench_detector)

        self.logger.info(
            f"Quench detector configured with thresholds: "
            f"energy={energy_threshold}, rate={rate_threshold}, "
            f"magnitude={magnitude_threshold}"
        )

    def get_quench_history(self) -> List[Dict]:
        """
        Get quench detection history.

        Returns:
            List[Dict]: History of detected quench events.
        """
        if self._quench_detector is None:
            return []
        return self._quench_detector.get_quench_history()

    def get_memory_contribution(self) -> np.ndarray:
        """
        Get current memory kernel contribution.

        Returns:
            np.ndarray: Current memory contribution to field.
        """
        if self._memory_kernel is None:
            return np.zeros(self.domain.shape, dtype=np.complex128)
        return self._memory_kernel.get_memory_contribution()
