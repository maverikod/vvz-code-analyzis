"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced BVP constants facade for material properties.

This module provides the main facade class for advanced BVP constants,
coordinating all components for material property calculations.

Physical Meaning:
    Contains advanced material properties and frequency-dependent
    calculations including nonlinear admittance coefficients, renormalized
    coefficients, and frequency-dependent material properties.

Mathematical Foundation:
    Implements advanced field theory calculations:
    - Nonlinear admittance coefficients with quantum corrections
    - Renormalized coefficients with renormalization group flow
    - Frequency-dependent material properties using Drude-Lorentz models

Example:
    >>> constants = BVPConstantsAdvanced()
    >>> coeffs = constants.compute_nonlinear_admittance_coefficients(freq, amp)
    >>> renormalized = constants.compute_renormalized_coefficients(amp, grad)
"""

import numpy as np
from typing import Dict, Any

from ..bvp_constants_base import BVPConstantsBase
from .frequency_dependent_properties import FrequencyDependentProperties
from .nonlinear_coefficients import NonlinearCoefficients
from .renormalized_coefficients import RenormalizedCoefficients


class BVPConstantsAdvanced(BVPConstantsBase):
    """
    Advanced material properties facade for BVP system.

    Physical Meaning:
        Extends base constants with advanced material properties and
        frequency-dependent calculations using full field theory.

    Mathematical Foundation:
        Implements advanced field theory calculations including:
        - Nonlinear admittance coefficients with quantum corrections
        - Renormalized coefficients with renormalization group flow
        - Frequency-dependent material properties using Drude-Lorentz models

    Attributes:
        frequency_properties (FrequencyDependentProperties): Frequency-dependent calculations.
        nonlinear_coeffs (NonlinearCoefficients): Nonlinear coefficient calculations.
        renormalized_coeffs (RenormalizedCoefficients): Renormalized coefficient calculations.
    """

    def __init__(self, config: Dict[str, Any] = None) -> None:
        """
        Initialize advanced BVP constants.

        Physical Meaning:
            Sets up advanced material properties and frequency-dependent
            calculation parameters.

        Args:
            config (Dict[str, Any], optional): Configuration to override defaults.
        """
        super().__init__(config)
        self._setup_advanced_material_constants()

        # Initialize components
        self.frequency_properties = FrequencyDependentProperties(self)
        self.nonlinear_coeffs = NonlinearCoefficients(self)
        self.renormalized_coeffs = RenormalizedCoefficients(self)

    def _setup_advanced_material_constants(self) -> None:
        """Setup advanced material property constants."""
        material_config = self.config.get("material_properties", {})

        # Nonlinear admittance coefficients
        self.ADMITTANCE_COEFF_1 = material_config.get("admittance_coeff_1", 0.1)
        self.ADMITTANCE_COEFF_2 = material_config.get("admittance_coeff_2", 0.01)
        self.ADMITTANCE_COEFF_3 = material_config.get("admittance_coeff_3", 0.001)
        self.ADMITTANCE_COEFF_4 = material_config.get("admittance_coeff_4", 0.0001)

        # Renormalized coefficients
        self.RENORM_COEFF_0 = material_config.get("renorm_coeff_0", 1.0)
        self.RENORM_COEFF_1 = material_config.get("renorm_coeff_1", 0.1)
        self.RENORM_COEFF_2 = material_config.get("renorm_coeff_2", 0.01)

        # Boundary condition coefficients
        self.BOUNDARY_PRESSURE_0 = material_config.get("boundary_pressure_0", 1.0)
        self.BOUNDARY_PRESSURE_1 = material_config.get("boundary_pressure_1", 0.1)
        self.BOUNDARY_STIFFNESS_0 = material_config.get("boundary_stiffness_0", 1.0)
        self.BOUNDARY_STIFFNESS_1 = material_config.get("boundary_stiffness_1", 0.1)

    def get_advanced_material_property(self, property_name: str) -> float:
        """
        Get advanced material property constant.

        Args:
            property_name (str): Name of the material property.

        Returns:
            float: Property value.
        """
        property_map = {
            "admittance_coeff_1": self.ADMITTANCE_COEFF_1,
            "admittance_coeff_2": self.ADMITTANCE_COEFF_2,
            "admittance_coeff_3": self.ADMITTANCE_COEFF_3,
            "admittance_coeff_4": self.ADMITTANCE_COEFF_4,
            "renorm_coeff_0": self.RENORM_COEFF_0,
            "renorm_coeff_1": self.RENORM_COEFF_1,
            "renorm_coeff_2": self.RENORM_COEFF_2,
            "boundary_pressure_0": self.BOUNDARY_PRESSURE_0,
            "boundary_pressure_1": self.BOUNDARY_PRESSURE_1,
            "boundary_stiffness_0": self.BOUNDARY_STIFFNESS_0,
            "boundary_stiffness_1": self.BOUNDARY_STIFFNESS_1,
        }
        return property_map.get(property_name, 0.0)

    def compute_frequency_dependent_conductivity(self, frequency: float) -> float:
        """
        Compute frequency-dependent conductivity using advanced Drude-Lorentz model.

        Physical Meaning:
            Computes conductivity using the Drude-Lorentz model for free electrons
            with frequency-dependent relaxation effects, including interband transitions
            and quantum corrections.

        Args:
            frequency (float): Frequency in rad/s.

        Returns:
            float: Frequency-dependent conductivity.
        """
        return self.frequency_properties.compute_conductivity(frequency)

    def compute_frequency_dependent_capacitance(self, frequency: float) -> float:
        """
        Compute frequency-dependent capacitance using advanced Debye-Cole model.

        Physical Meaning:
            Computes capacitance using the Debye-Cole model for dielectric
            relaxation with frequency-dependent polarization, including
            multiple relaxation times and Cole-Cole distribution.

        Args:
            frequency (float): Frequency in rad/s.

        Returns:
            float: Frequency-dependent capacitance.
        """
        return self.frequency_properties.compute_capacitance(frequency)

    def compute_frequency_dependent_inductance(self, frequency: float) -> float:
        """
        Compute frequency-dependent inductance using advanced skin effect and proximity models.

        Physical Meaning:
            Computes inductance considering skin effect, proximity effect,
            and frequency-dependent magnetic field penetration with
            quantum corrections and eddy current losses.

        Args:
            frequency (float): Frequency in rad/s.

        Returns:
            float: Frequency-dependent inductance.
        """
        return self.frequency_properties.compute_inductance(frequency)

    def compute_nonlinear_admittance_coefficients(
        self, frequency: float, amplitude: float
    ) -> Dict[str, float]:
        """
        Compute nonlinear admittance coefficients using advanced field theory.

        Physical Meaning:
            Computes frequency and amplitude dependent coefficients for
            nonlinear admittance using full electromagnetic field theory
            including quantum corrections and many-body effects.

        Args:
            frequency (float): Frequency in rad/s.
            amplitude (float): Field amplitude |A|.

        Returns:
            Dict[str, float]: Nonlinear admittance coefficients.
        """
        return self.nonlinear_coeffs.compute_admittance_coefficients(
            frequency, amplitude
        )

    def compute_renormalized_coefficients(
        self, amplitude: float, gradient_magnitude_squared: float
    ) -> Dict[str, float]:
        """
        Compute renormalized coefficients using advanced field theory.

        Physical Meaning:
            Computes amplitude and gradient dependent coefficients
            using full quantum field theory with renormalization group
            methods and effective field theory.

        Args:
            amplitude (float): Field amplitude |A|.
            gradient_magnitude_squared (float): Gradient magnitude squared |∇A|².

        Returns:
            Dict[str, float]: Renormalized coefficients.
        """
        return self.renormalized_coeffs.compute_renormalized_coefficients(
            amplitude, gradient_magnitude_squared
        )

    def __repr__(self) -> str:
        """String representation of advanced BVP constants."""
        return (
            f"BVPConstantsAdvanced(carrier_freq={self.CARRIER_FREQUENCY}, "
            f"kappa_0={self.KAPPA_0}, kappa_2={self.KAPPA_2})"
        )
