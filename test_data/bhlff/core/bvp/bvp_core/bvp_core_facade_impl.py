"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Core Facade Implementation - Main implementation for BVP framework.

This module provides the main implementation for the BVP framework facade,
implementing all core operations for BVP envelope solving, quench detection,
and impedance computation.

Physical Meaning:
    The BVP Core Facade Implementation provides the concrete implementation
    for the central backbone of the entire system, where all observed
    particles and fields are manifestations of envelope modulations
    and beatings of the high-frequency carrier field.

Mathematical Foundation:
    BVP implements the envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
    χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.

Example:
    >>> bvp_core = BVPCoreFacade(domain, config, domain_7d)
    >>> envelope = bvp_core.solve_envelope(source)
    >>> quenches = bvp_core.detect_quenches(envelope)
"""

import numpy as np
from typing import Dict, Any, Optional, Union
import logging

from ...domain import Domain
from ...domain.domain_7d import Domain7D
from ..abstract_bvp_facade import AbstractBVPFacade
from ..bvp_constants import BVPConstants
from .bvp_operations import BVPCoreOperations
from .bvp_7d_interface import BVPCore7DInterface


class BVPCoreFacade(AbstractBVPFacade):
    """
    BVP Core Facade - Main implementation for BVP framework.

    Physical Meaning:
        Provides the concrete implementation for the central backbone of the
        entire system, where all observed particles and fields are manifestations
        of envelope modulations and beatings of the high-frequency carrier field.

    Mathematical Foundation:
        BVP implements the envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
        where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
        χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.
    """

    def __init__(
        self,
        domain: Domain,
        config: Dict[str, Any],
        domain_7d: Optional[Domain7D] = None,
    ):
        """
        Initialize BVP core facade implementation.

        Physical Meaning:
            Sets up the concrete implementation for the BVP framework with
            computational domains and configuration parameters, initializing
            all necessary components for BVP operations.

        Args:
            domain (Domain): Standard computational domain for BVP operations.
            config (Dict[str, Any]): Configuration parameters including:
                - carrier_frequency: BVP carrier frequency
                - kappa_0, kappa_2: Stiffness coefficients
                - chi_prime, chi_double_prime_0: Susceptibility coefficients
                - k0: Wave number
            domain_7d (Optional[Domain7D]): 7D computational domain for
                full space-time operations.
        """
        super().__init__(domain, config, domain_7d)

        # Validate configuration
        if not self.validate_configuration():
            raise ValueError("Invalid BVP configuration parameters")

        # Initialize BVP constants
        self._bvp_constants = BVPConstants(config)

        # Initialize core operations
        self._operations = BVPCoreOperations(domain, config, domain_7d)

        # Initialize 7D interface if 7D domain is available
        self._7d_interface = None
        if domain_7d is not None:
            self._7d_interface = BVPCore7DInterface(domain_7d, config)

        self.logger.info("BVP Core Facade initialized")

    def solve_envelope(self, source: np.ndarray) -> np.ndarray:
        """
        Solve BVP envelope equation for U(1)³ phase structure.

        Physical Meaning:
            Computes the envelope a(x,φ,t) of the Base High-Frequency Field
            in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ that modulates the high-frequency carrier.
            The envelope is a vector of three U(1) phase components Θ_a (a=1..3).

        Mathematical Foundation:
            Solves ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) for the envelope a(x,φ,t)
            where a is a vector of three U(1) phase components in 7D space-time.

        Args:
            source (np.ndarray): Source term s(x,φ,t) in 7D space-time.
                Represents external excitations or initial conditions in M₇.

        Returns:
            np.ndarray: BVP envelope a(x,φ,t) in 7D space-time.
                Represents the envelope modulation of the high-frequency carrier
                as a vector of three U(1) phase components.

        Raises:
            ValueError: If source has incompatible shape with 7D domain.
        """
        return self._operations.solve_envelope(source)

    def solve_envelope_7d(self, source_7d: np.ndarray) -> np.ndarray:
        """
        Solve 7D BVP envelope equation.

        Physical Meaning:
            Solves the full 7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            using the 7D envelope equation solver. This provides the complete
            solution including spatial, phase, and temporal evolution.

        Args:
            source_7d (np.ndarray): 7D source term s(x,φ,t).

        Returns:
            np.ndarray: 7D envelope solution a(x,φ,t).
        """
        if self._7d_interface is None:
            raise ValueError("7D interface not available - domain_7d was not provided")

        # Use 7D operations from core operations
        operations_7d = self._operations.get_7d_operations()
        if operations_7d is None:
            raise ValueError("7D operations not available - domain_7d was not provided")

        return operations_7d.solve_envelope_7d(source_7d)

    def validate_postulates_7d(self, envelope_7d: np.ndarray) -> Dict[str, Any]:
        """
        Validate all 9 BVP postulates in 7D space-time.

        Physical Meaning:
            Validates all 9 BVP postulates against the 7D envelope solution,
            ensuring physical consistency and theoretical correctness.

        Args:
            envelope_7d (np.ndarray): 7D envelope solution to validate.

        Returns:
            Dict[str, Any]: Postulate validation results.
        """
        if self._7d_interface is None:
            raise ValueError("7D interface not available - domain_7d was not provided")

        # Use 7D operations from core operations
        operations_7d = self._operations.get_7d_operations()
        if operations_7d is None:
            raise ValueError("7D operations not available - domain_7d was not provided")

        return operations_7d.validate_postulates_7d(envelope_7d)

    def detect_quenches(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Detect quench events when local thresholds are reached.

        Physical Meaning:
            Identifies when BVP dissipatively "dumps" energy into
            the medium at local thresholds (amplitude/detuning/gradient).

        Mathematical Foundation:
            Applies three threshold criteria:
            - amplitude: |A| > |A_q|
            - detuning: |ω - ω_0| > Δω_q
            - gradient: |∇A| > |∇A_q|

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Quench detection results including:
                - quench_locations: Spatial locations of quenches
                - quench_types: Types of quenches detected
                - energy_dumped: Energy dumped at each quench
        """
        return self._operations.detect_quenches(envelope)

    def compute_impedance(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute impedance/admittance from BVP envelope.

        Physical Meaning:
            Calculates Y(ω), R(ω), T(ω), and peaks {ω_n,Q_n}
            from the BVP envelope at boundaries.

        Mathematical Foundation:
            Computes boundary functions from BVP envelope:
            - Admittance: Y(ω) = I(ω)/V(ω)
            - Reflection: R(ω) = |r(ω)|²
            - Transmission: T(ω) = |t(ω)|²
            - Resonances: {ω_n,Q_n} from spectral analysis

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Impedance calculation results including:
                - admittance: Y(ω) frequency response
                - reflection: R(ω) reflection coefficients
                - transmission: T(ω) transmission coefficients
                - resonances: {ω_n,Q_n} resonance frequencies and Q-factors
        """
        return self._operations.compute_impedance(envelope)

    def get_phase_vector(self) -> Optional[np.ndarray]:
        """
        Get U(1)³ phase vector structure.

        Physical Meaning:
            Retrieves the U(1)³ phase vector Θ = (Θ₁, Θ₂, Θ₃) representing
            the three independent U(1) phase degrees of freedom.

        Returns:
            Optional[np.ndarray]: U(1)³ phase vector or None if not available.
        """
        if hasattr(self._operations, "get_phase_vector"):
            return self._operations.get_phase_vector()
        return None

    def get_bvp_constants(self) -> BVPConstants:
        """
        Get BVP constants and configuration.

        Physical Meaning:
            Retrieves the BVP constants and configuration parameters
            used in the framework.

        Returns:
            BVPConstants: BVP constants instance.
        """
        return self._bvp_constants

    def get_7d_interface(self) -> Optional[BVPCore7DInterface]:
        """
        Get 7D interface if available.

        Physical Meaning:
            Retrieves the 7D interface for full space-time operations
            if a 7D domain was provided during initialization.

        Returns:
            Optional[BVPCore7DInterface]: 7D interface or None if not available.
        """
        return self._7d_interface

    def get_phase_operations(self):
        """
        Get phase operations interface.

        Physical Meaning:
            Retrieves the phase operations interface for U(1)³ phase
            structure analysis and manipulation.

        Returns:
            Phase operations interface.
        """
        return self._operations.get_phase_operations()

    def get_parameter_access(self):
        """
        Get parameter access interface.

        Physical Meaning:
            Retrieves the parameter access interface for BVP constants
            and configuration management.

        Returns:
            Parameter access interface.
        """
        return self._operations.get_parameter_access()

    def __repr__(self) -> str:
        """String representation of BVP core facade."""
        return (
            f"{self.__class__.__name__}("
            f"domain={self.domain.shape}, "
            f"has_7d={self.domain_7d is not None}, "
            f"config_keys={list(self.config.keys())})"
        )
