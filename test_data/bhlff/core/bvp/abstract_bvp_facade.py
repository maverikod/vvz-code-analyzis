"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Abstract base class for BVP facades.

This module provides the abstract base class for all BVP facades,
defining the common interface and shared functionality for BVP
envelope solving, quench detection, and impedance computation.

Physical Meaning:
    Defines the fundamental interface for the central backbone of the
    entire system, where all observed particles and fields are
    manifestations of envelope modulations and beatings of the
    high-frequency carrier field.

Mathematical Foundation:
    BVP implements the envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
    χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.

Example:
    >>> class MyBVPFacade(AbstractBVPFacade):
    ...     def solve_envelope(self, source):
    ...         # Implementation
    ...     def detect_quenches(self, envelope):
    ...         # Implementation
"""

import numpy as np
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging

from ..domain import Domain
from ..domain.domain_7d import Domain7D


class AbstractBVPFacade(ABC):
    """
    Abstract base class for BVP facades.

    Physical Meaning:
        Defines the interface for the central backbone of the entire system,
        where all observed particles and fields are manifestations of envelope
        modulations and beatings of the high-frequency carrier field.

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
        Initialize abstract BVP facade.

        Physical Meaning:
            Sets up the base interface for the BVP framework with computational
            domains and configuration parameters.

        Args:
            domain (Domain): Standard computational domain for BVP operations.
            config (Dict[str, Any]): Configuration parameters.
            domain_7d (Optional[Domain7D]): 7D computational domain.
        """
        self.domain = domain
        self.config = config
        self.domain_7d = domain_7d
        self.logger = logging.getLogger(self.__class__.__name__)

        self.logger.info(
            f"{self.__class__.__name__} initialized for domain {domain.shape}"
        )

    @abstractmethod
    def solve_envelope(self, source: np.ndarray) -> np.ndarray:
        """
        Solve BVP envelope equation for U(1)³ phase structure.

        Physical Meaning:
            Computes the envelope a(x,φ,t) of the Base High-Frequency Field
            in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ that modulates the high-frequency carrier.

        Args:
            source (np.ndarray): Source term s(x,φ,t) in 7D space-time.

        Returns:
            np.ndarray: BVP envelope a(x,φ,t) in 7D space-time.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement solve_envelope method")

    @abstractmethod
    def detect_quenches(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Detect quench events when local thresholds are reached.

        Physical Meaning:
            Identifies when BVP dissipatively "dumps" energy into
            the medium at local thresholds (amplitude/detuning/gradient).

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Quench detection results.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement detect_quenches method")

    @abstractmethod
    def compute_impedance(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute impedance/admittance from BVP envelope.

        Physical Meaning:
            Calculates Y(ω), R(ω), T(ω), and peaks {ω_n,Q_n}
            from the BVP envelope at boundaries.

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Impedance calculation results.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement compute_impedance method")

    def get_phase_vector(self) -> Optional[np.ndarray]:
        """
        Get U(1)³ phase vector structure.

        Physical Meaning:
            Retrieves the U(1)³ phase vector Θ = (Θ₁, Θ₂, Θ₃) representing
            the three independent U(1) phase degrees of freedom.

        Returns:
            Optional[np.ndarray]: U(1)³ phase vector or None if not available.
        """
        # Default implementation returns None
        # Subclasses should override if phase vector is available
        return None

    def validate_configuration(self) -> bool:
        """
        Validate BVP configuration parameters.

        Physical Meaning:
            Ensures that the BVP configuration parameters are physically
            meaningful and mathematically consistent.

        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        required_keys = ["carrier_frequency", "envelope_equation"]

        for key in required_keys:
            if key not in self.config:
                self.logger.error(f"Missing required configuration key: {key}")
                return False

        # Validate envelope equation parameters
        env_eq = self.config.get("envelope_equation", {})
        required_env_keys = ["kappa_0", "kappa_2", "chi_prime"]

        for key in required_env_keys:
            if key not in env_eq:
                self.logger.error(
                    f"Missing required envelope equation parameter: {key}"
                )
                return False

        return True

    def is_7d_available(self) -> bool:
        """
        Check if 7D domain is available.

        Physical Meaning:
            Determines whether the 7D computational domain is available
            for full space-time operations.

        Returns:
            bool: True if 7D domain is available, False otherwise.
        """
        return self.domain_7d is not None

    def get_7d_domain(self) -> Optional[Domain7D]:
        """
        Get 7D domain if available.

        Physical Meaning:
            Retrieves the 7D computational domain for full space-time
            operations if available.

        Returns:
            Optional[Domain7D]: 7D domain or None if not available.
        """
        return self.domain_7d

    def get_domain_info(self) -> Dict[str, Any]:
        """
        Get domain information.

        Physical Meaning:
            Returns comprehensive information about the computational
            domains used by the BVP facade.

        Returns:
            Dict[str, Any]: Domain information including shapes and types.
        """
        info = {
            "standard_domain_shape": self.domain.shape,
            "standard_domain_type": type(self.domain).__name__,
            "7d_available": self.is_7d_available(),
        }

        if self.is_7d_available():
            info.update(
                {
                    "7d_domain_shape": self.domain_7d.shape,
                    "7d_domain_type": type(self.domain_7d).__name__,
                }
            )

        return info

    def get_configuration_info(self) -> Dict[str, Any]:
        """
        Get configuration information.

        Physical Meaning:
            Returns information about the BVP configuration parameters
            for monitoring and analysis purposes.

        Returns:
            Dict[str, Any]: Configuration information.
        """
        return {
            "config_keys": list(self.config.keys()),
            "is_valid": self.validate_configuration(),
            "has_envelope_equation": "envelope_equation" in self.config,
            "has_carrier_frequency": "carrier_frequency" in self.config,
        }

    def validate_configuration(self) -> bool:
        """
        Validate BVP configuration parameters.

        Physical Meaning:
            Validates that all required configuration parameters
            are present and have valid values for BVP operations.

        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        # Check if envelope_equation is present
        if "envelope_equation" not in self.config:
            return False

        # Check if carrier_frequency is present
        if "carrier_frequency" not in self.config:
            return False

        # Get envelope equation config
        envelope_config = self.config.get("envelope_equation", {})

        # Check if envelope equation config is a dictionary
        if not isinstance(envelope_config, dict):
            return False

        # Check if all required envelope parameters are present
        required_envelope_keys = [
            "kappa_0",
            "kappa_2",
            "chi_prime",
            "chi_double_prime_0",
            "k0_squared",
        ]

        for key in required_envelope_keys:
            if key not in envelope_config:
                return False

        # Check if values are valid
        try:
            if self.config["carrier_frequency"] <= 0:
                return False
            if envelope_config["kappa_0"] <= 0:
                return False
            if envelope_config["kappa_2"] < 0:
                return False
            if envelope_config["k0_squared"] <= 0:
                return False
        except (TypeError, ValueError):
            return False

        return True

    def __repr__(self) -> str:
        """String representation of BVP facade."""
        return (
            f"{self.__class__.__name__}("
            f"domain={self.domain.shape}, "
            f"has_7d={self.is_7d_available()}, "
            f"config_keys={len(self.config)})"
        )
