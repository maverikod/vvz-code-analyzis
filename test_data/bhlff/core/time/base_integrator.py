"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base time integrator for 7D BVP framework.

This module implements the abstract base class for all temporal integrators
in the 7D BVP framework, providing common interfaces and functionality
for solving dynamic phase field equations.

Physical Meaning:
    Base integrators provide the fundamental interface for solving
    dynamic phase field equations in 7D space-time, including support
    for memory kernels and quench detection.

Mathematical Foundation:
    All integrators implement methods for solving the dynamic equation:
    ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
    in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import numpy as np
import logging

from ..domain import Domain
from ..domain.parameters import Parameters


class BaseTimeIntegrator(ABC):
    """
    Abstract base class for 7D BVP time integrators.

    Physical Meaning:
        Provides the fundamental interface for all temporal integrators
        in the 7D BVP framework, ensuring consistent behavior across
        different numerical methods and physical regimes.

    Mathematical Foundation:
        All integrators implement methods for solving the dynamic equation:
        ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
        in 7D space-time with support for memory kernels and quench detection.

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _initialized (bool): Initialization status.
        _memory_kernel (Optional[MemoryKernel]): Memory kernel for non-local effects.
        _quench_detector (Optional[QuenchDetector]): Quench detection system.
    """

    def __init__(self, domain: Domain, parameters: Parameters) -> None:
        """
        Initialize base time integrator.

        Physical Meaning:
            Sets up the integrator with the computational domain and
            physics parameters, preparing for temporal integration of
            the dynamic phase field equation.

        Args:
            domain (Domain): Computational domain for the simulation.
            parameters (Parameters): Physics parameters controlling
                the behavior of the phase field system.
        """
        self.domain = domain
        self.parameters = parameters
        self._initialized = False
        self._memory_kernel = None
        self._quench_detector = None

        # Validate parameters
        self._validate_parameters()

        # Setup logging
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def integrate(
        self,
        initial_field: np.ndarray,
        source_field: np.ndarray,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate the dynamic equation over time.

        Physical Meaning:
            Solves the dynamic phase field equation over the specified
            time steps, representing the temporal evolution of the phase
            field configuration in 7D space-time.

        Mathematical Foundation:
            Integrates the equation:
            ∂a/∂t + ν(-Δ)^β a + λa = s(x,φ,t)
            with initial condition a(x,φ,0) = initial_field(x,φ).

        Args:
            initial_field (np.ndarray): Initial field configuration a(x,φ,0).
            source_field (np.ndarray): Source term s(x,φ,t) over time.
            time_steps (np.ndarray): Time points for integration.

        Returns:
            np.ndarray: Field evolution a(x,φ,t) over time.

        Raises:
            ValueError: If input fields have incompatible shapes.
            RuntimeError: If integration fails.
        """
        raise NotImplementedError("Subclasses must implement integrate method")

    @abstractmethod
    def step(
        self, current_field: np.ndarray, source_field: np.ndarray, dt: float
    ) -> np.ndarray:
        """
        Perform a single time step.

        Physical Meaning:
            Advances the field configuration by one time step,
            representing the local temporal evolution of the phase field.

        Args:
            current_field (np.ndarray): Current field configuration.
            source_field (np.ndarray): Source term at current time.
            dt (float): Time step size.

        Returns:
            np.ndarray: Field configuration at next time step.
        """
        raise NotImplementedError("Subclasses must implement step method")

    def set_memory_kernel(self, memory_kernel: "MemoryKernel") -> None:
        """
        Set memory kernel for non-local effects.

        Physical Meaning:
            Configures the memory kernel to account for non-local
            temporal effects in the phase field evolution.

        Args:
            memory_kernel (MemoryKernel): Memory kernel instance.
        """
        self._memory_kernel = memory_kernel
        self.logger.info("Memory kernel set")

    def set_quench_detector(self, quench_detector: "QuenchDetector") -> None:
        """
        Set quench detection system.

        Physical Meaning:
            Configures the quench detection system to monitor
            for energy dumping events during integration.

        Args:
            quench_detector (QuenchDetector): Quench detector instance.
        """
        self._quench_detector = quench_detector
        self.logger.info("Quench detector set")

    def _validate_parameters(self) -> None:
        """
        Validate integrator parameters.

        Physical Meaning:
            Ensures all physical parameters are within valid ranges
            for the dynamic phase field equation.
        """
        if self.parameters.nu <= 0:
            raise ValueError(
                f"Diffusion coefficient ν must be positive, got {self.parameters.nu}"
            )

        if not (0 < self.parameters.beta < 2):
            raise ValueError(
                f"Fractional order β must be in (0,2), got {self.parameters.beta}"
            )

        if self.parameters.lambda_param < 0:
            raise ValueError(
                f"Damping parameter λ must be non-negative, got {self.parameters.lambda_param}"
            )

    def _check_quench(self, field: np.ndarray, time: float) -> bool:
        """
        Check for quench events.

        Physical Meaning:
            Monitors the field for energy dumping events that may
            require special handling during integration.

        Args:
            field (np.ndarray): Current field configuration.
            time (float): Current time.

        Returns:
            bool: True if quench detected, False otherwise.
        """
        if self._quench_detector is None:
            return False

        return self._quench_detector.detect_quench(field, time)

    def _apply_memory_kernel(self, field: np.ndarray, time: float) -> np.ndarray:
        """
        Apply memory kernel effects.

        Physical Meaning:
            Applies non-local temporal effects through the memory kernel,
            accounting for the system's memory of past configurations.

        Args:
            field (np.ndarray): Current field configuration.
            time (float): Current time.

        Returns:
            np.ndarray: Field with memory kernel effects applied.
        """
        if self._memory_kernel is None:
            return field

        return self._memory_kernel.apply(field, time)

    @property
    def is_initialized(self) -> bool:
        """Check if integrator is initialized."""
        return self._initialized

    def __repr__(self) -> str:
        """String representation of integrator."""
        return (
            f"{self.__class__.__name__}("
            f"domain={self.domain.shape}, "
            f"nu={self.parameters.nu}, "
            f"beta={self.parameters.beta}, "
            f"lambda={self.parameters.lambda_param})"
        )
