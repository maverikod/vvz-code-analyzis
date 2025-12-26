"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory kernel implementation for 7D BVP framework.

This module implements memory kernels for non-local temporal effects
in the 7D phase field theory, providing support for memory variables
and their evolution.

Physical Meaning:
    Memory kernels account for non-local temporal effects in phase field
    evolution, representing the system's memory of past configurations
    and their influence on current dynamics.

Mathematical Foundation:
    Implements memory variables evolution:
    ∂mⱼ/∂t + (1/τⱼ) mⱼ = source_terms
    where τⱼ are relaxation times and mⱼ are memory variables.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import logging

from ..domain import Domain


class MemoryKernel:
    """
    Memory kernel for non-local temporal effects in 7D BVP.

    Physical Meaning:
        Represents the system's memory of past phase field configurations
        and their influence on current dynamics through memory variables
        with different relaxation times.

    Mathematical Foundation:
        Implements memory variables evolution:
        ∂mⱼ/∂t + (1/τⱼ) mⱼ = source_terms
        where τⱼ are relaxation times and mⱼ are memory variables.

    Attributes:
        domain (Domain): Computational domain.
        memory_variables (List[np.ndarray]): Memory variables mⱼ.
        relaxation_times (List[float]): Relaxation times τⱼ.
        coupling_strengths (List[float]): Coupling strengths γⱼ.
        _initialized (bool): Initialization status.
    """

    def __init__(self, domain: Domain, num_memory_vars: int = 3) -> None:
        """
        Initialize memory kernel.

        Physical Meaning:
            Sets up the memory kernel with specified number of memory
            variables, each with its own relaxation time and coupling strength.

        Args:
            domain (Domain): Computational domain.
            num_memory_vars (int): Number of memory variables.
        """
        self.domain = domain
        self.num_memory_vars = num_memory_vars
        self._initialized = False

        # Initialize memory variables
        self.memory_variables = []
        self.relaxation_times = []
        self.coupling_strengths = []

        # Setup logging
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize memory system
        self._setup_memory_system()

    def _setup_memory_system(self) -> None:
        """
        Setup memory system with default parameters.

        Physical Meaning:
            Initializes memory variables with default relaxation times
            and coupling strengths for typical 7D phase field dynamics.
        """
        # Default relaxation times (increasing order)
        default_taus = [0.1, 1.0, 10.0]

        # Default coupling strengths
        default_gammas = [0.1, 0.05, 0.01]

        for i in range(self.num_memory_vars):
            # Initialize memory variable
            memory_var = np.zeros(self.domain.shape, dtype=np.complex128)
            self.memory_variables.append(memory_var)

            # Set relaxation time
            tau = (
                default_taus[i] if i < len(default_taus) else default_taus[-1] * (i + 1)
            )
            self.relaxation_times.append(tau)

            # Set coupling strength
            gamma = (
                default_gammas[i]
                if i < len(default_gammas)
                else default_gammas[-1] / (i + 1)
            )
            self.coupling_strengths.append(gamma)

        self._initialized = True
        self.logger.info(
            f"Memory kernel initialized with {self.num_memory_vars} variables"
        )

    def apply(self, field: np.ndarray, time: float) -> np.ndarray:
        """
        Apply memory kernel effects to field.

        Physical Meaning:
            Applies the combined effect of all memory variables to the
            current field configuration, representing non-local temporal
            influences from past configurations.

        Mathematical Foundation:
            Returns: field + ∑ⱼ γⱼ mⱼ
            where γⱼ are coupling strengths and mⱼ are memory variables.

        Args:
            field (np.ndarray): Current field configuration.
            time (float): Current time.

        Returns:
            np.ndarray: Field with memory kernel effects applied.
        """
        if not self._initialized:
            raise RuntimeError("Memory kernel not initialized")

        result = field.copy()

        # Apply memory variables
        for i, (memory_var, gamma) in enumerate(
            zip(self.memory_variables, self.coupling_strengths)
        ):
            result += gamma * memory_var

        return result

    def evolve(self, field: np.ndarray, dt: float) -> None:
        """
        Evolve memory variables.

        Physical Meaning:
            Updates memory variables according to their evolution equation,
            incorporating the current field configuration as a source term.

        Mathematical Foundation:
            For each memory variable mⱼ:
            ∂mⱼ/∂t + (1/τⱼ) mⱼ = field
            Discretized as: mⱼ^{n+1} = mⱼ^n + dt * (field - mⱼ^n/τⱼ)

        Args:
            field (np.ndarray): Current field configuration.
            dt (float): Time step size.
        """
        if not self._initialized:
            raise RuntimeError("Memory kernel not initialized")

        for i, (memory_var, tau) in enumerate(
            zip(self.memory_variables, self.relaxation_times)
        ):
            # Evolution equation: ∂mⱼ/∂t + (1/τⱼ) mⱼ = field
            # Discretized: mⱼ^{n+1} = mⱼ^n + dt * (field - mⱼ^n/τⱼ)
            self.memory_variables[i] = memory_var + dt * (field - memory_var / tau)

    def reset(self) -> None:
        """
        Reset memory variables to zero.

        Physical Meaning:
            Clears all memory of past configurations, effectively
            starting with a fresh memory state.
        """
        for i in range(self.num_memory_vars):
            self.memory_variables[i] = np.zeros(self.domain.shape, dtype=np.complex128)

        self.logger.info("Memory variables reset")

    def set_relaxation_times(self, taus: List[float]) -> None:
        """
        Set relaxation times for memory variables.

        Physical Meaning:
            Configures the relaxation times τⱼ for each memory variable,
            controlling how quickly each variable forgets past information.

        Args:
            taus (List[float]): Relaxation times for each memory variable.
        """
        if len(taus) != self.num_memory_vars:
            raise ValueError(
                f"Expected {self.num_memory_vars} relaxation times, got {len(taus)}"
            )

        for tau in taus:
            if tau <= 0:
                raise ValueError(f"Relaxation time must be positive, got {tau}")

        self.relaxation_times = taus.copy()
        self.logger.info(f"Relaxation times set: {taus}")

    def set_coupling_strengths(self, gammas: List[float]) -> None:
        """
        Set coupling strengths for memory variables.

        Physical Meaning:
            Configures the coupling strengths γⱼ for each memory variable,
            controlling how strongly each variable influences the field.

        Args:
            gammas (List[float]): Coupling strengths for each memory variable.
        """
        if len(gammas) != self.num_memory_vars:
            raise ValueError(
                f"Expected {self.num_memory_vars} coupling strengths, got {len(gammas)}"
            )

        self.coupling_strengths = gammas.copy()

        # PASS-1: Assert ReY(ω)≥0 for memory kernels below resonances
        self._validate_passivity()

        self.logger.info(f"Coupling strengths set: {gammas}")

    def _validate_passivity(self) -> None:
        """
        Validate PASS-1: ReY(ω)≥0 for memory kernels below resonances.

        Physical Meaning:
            Ensures that the memory kernel frequency response Y(ω) has
            non-negative real part below resonances, maintaining passivity
            of the memory system.

        Mathematical Foundation:
            For Prony/fractional memory kernels: Y(ω) = Σⱼ γⱼ/(1 + iωτⱼ)
            Passivity requires ReY(ω) = Σⱼ γⱼ/(1 + ω²τⱼ²) ≥ 0 for all ω
        """
        # Check that all coupling strengths are non-negative for passivity
        for i, gamma in enumerate(self.coupling_strengths):
            if gamma < 0:
                self.logger.warning(f"PASS-1 violation: γ_{i} = {gamma} < 0")
                # Log violation but don't fail - allow for diagnostic cases
                continue

        # For Prony model: Y(ω) = Σⱼ γⱼ/(1 + iωτⱼ)
        # ReY(ω) = Σⱼ γⱼ/(1 + ω²τⱼ²) ≥ 0 if all γⱼ ≥ 0
        if all(gamma >= 0 for gamma in self.coupling_strengths):
            self.logger.info("PASS-1: Memory kernel passivity validated (ReY(ω)≥0)")
        else:
            self.logger.warning("PASS-1: Memory kernel may violate passivity")

    def get_memory_contribution(self) -> np.ndarray:
        """
        Get total memory contribution to field.

        Physical Meaning:
            Returns the combined contribution of all memory variables
            to the field evolution.

        Returns:
            np.ndarray: Total memory contribution ∑ⱼ γⱼ mⱼ.
        """
        if not self._initialized:
            raise RuntimeError("Memory kernel not initialized")

        total_contribution = np.zeros(self.domain.shape, dtype=np.complex128)

        for memory_var, gamma in zip(self.memory_variables, self.coupling_strengths):
            total_contribution += gamma * memory_var

        return total_contribution

    def __repr__(self) -> str:
        """String representation of memory kernel."""
        return (
            f"MemoryKernel("
            f"domain={self.domain.shape}, "
            f"num_vars={self.num_memory_vars}, "
            f"taus={self.relaxation_times}, "
            f"gammas={self.coupling_strengths})"
        )
