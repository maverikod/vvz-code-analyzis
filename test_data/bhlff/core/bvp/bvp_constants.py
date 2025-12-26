"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP constants facade - unified interface for all BVP constants.

This module provides a unified interface to all BVP constants by combining
base constants, advanced material properties, and numerical parameters.

Physical Meaning:
    Provides a single interface to access all physical constants, numerical
    parameters, and configuration defaults for the BVP system.

Mathematical Foundation:
    Combines constants from multiple modules:
    - Base envelope equation parameters
    - Advanced material properties with frequency dependence
    - Numerical solver parameters and thresholds

Example:
    >>> constants = BVPConstants()
    >>> kappa_0 = constants.get_envelope_parameter('kappa_0')
    >>> sigma_em = constants.get_material_property('em_conductivity')
    >>> coeffs = constants.compute_nonlinear_admittance_coefficients(freq, amp)
"""

import numpy as np
from typing import Dict, Any, Tuple

from .bvp_constants_base import BVPConstantsBase
from .constants.bvp_constants_advanced import BVPConstantsAdvanced
from .bvp_constants_numerical import BVPConstantsNumerical


class BVPConstants(BVPConstantsNumerical, BVPConstantsAdvanced, BVPConstantsBase):
    """
    Unified interface for all BVP constants.

    Physical Meaning:
        Provides a single interface to access all physical constants, numerical
        parameters, and configuration defaults for the BVP system by combining
        base constants, advanced material properties, and numerical parameters.

    Mathematical Foundation:
        Combines constants from multiple modules:
        - Base envelope equation parameters
        - Advanced material properties with frequency dependence
        - Numerical solver parameters and thresholds
    """

    def __init__(self, config: Dict[str, Any] = None) -> None:
        """
        Initialize unified BVP constants.

        Physical Meaning:
            Sets up all BVP constants by initializing base, advanced, and
            numerical constant modules with the provided configuration.

        Args:
            config (Dict[str, Any], optional): Configuration to override defaults.
        """
        # Initialize all parent classes with the same config
        BVPConstantsBase.__init__(self, config)
        BVPConstantsAdvanced.__init__(self, config)
        BVPConstantsNumerical.__init__(self, config)

    def get_material_property(self, property_name: str) -> float:
        """
        Get material property constant (unified interface).

        Physical Meaning:
            Provides unified access to both basic and advanced material
            properties through a single interface.

        Args:
            property_name (str): Name of the material property.

        Returns:
            float: Property value.
        """
        # Try basic material properties first
        basic_property = self.get_basic_material_property(property_name)
        if basic_property != 0.0:
            return basic_property

        # Try advanced material properties
        return self.get_advanced_material_property(property_name)

    def get_all_constants(self) -> Dict[str, Any]:
        """
        Get all BVP constants as a dictionary.

        Physical Meaning:
            Returns all BVP constants for monitoring and analysis purposes.

        Returns:
            Dict[str, Any]: Dictionary containing all constants.
        """
        return {
            # Envelope equation parameters
            "kappa_0": self.KAPPA_0,
            "kappa_2": self.KAPPA_2,
            "chi_prime": self.CHI_PRIME,
            "chi_double_prime_0": self.CHI_DOUBLE_PRIME_0,
            "k0_squared": self.K0_SQUARED,
            "carrier_frequency": self.CARRIER_FREQUENCY,
            # Quench detection thresholds
            "amplitude_threshold": self.AMPLITUDE_THRESHOLD,
            "detuning_threshold": self.DETUNING_THRESHOLD,
            "gradient_threshold": self.GRADIENT_THRESHOLD,
            # Physical constants
            "speed_of_light": self.SPEED_OF_LIGHT,
            "vacuum_permeability": self.VACUUM_PERMEABILITY,
            "vacuum_permittivity": self.VACUUM_PERMITTIVITY,
            "planck_constant": self.PLANCK_CONSTANT,
            "boltzmann_constant": self.BOLTZMANN_CONSTANT,
        }

    def __repr__(self) -> str:
        """String representation of unified BVP constants."""
        return (
            f"BVPConstants(carrier_freq={self.CARRIER_FREQUENCY}, "
            f"kappa_0={self.KAPPA_0}, kappa_2={self.KAPPA_2})"
        )
