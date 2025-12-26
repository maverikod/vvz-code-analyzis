"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base BVP constants and configuration parameters.

This module defines the base physical constants and configuration parameters
for the BVP (Base High-Frequency Field) system.

Physical Meaning:
    Contains the fundamental physical constants and basic configuration
    parameters required for the BVP system initialization.

Mathematical Foundation:
    Defines base constants for:
    - Envelope equation parameters (κ₀, κ₂, χ', χ'')
    - Basic material properties
    - Fundamental physical constants

Example:
    >>> constants = BVPConstantsBase()
    >>> kappa_0 = constants.get_envelope_parameter('kappa_0')
    >>> speed_of_light = constants.get_physical_constant('speed_of_light')
"""

import numpy as np
from typing import Dict, Any, Optional


class BVPConstantsBase:
    """
    Base physical constants and configuration parameters for BVP system.

    Physical Meaning:
        Centralized storage for fundamental physical constants and basic
        configuration parameters used throughout the BVP system.

    Mathematical Foundation:
        Organizes base constants by physical category:
        - Envelope equation parameters
        - Basic material properties
        - Fundamental physical constants
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize base BVP constants with optional configuration override.

        Physical Meaning:
            Sets up fundamental physical constants with values from configuration
            or uses scientifically accurate defaults.

        Args:
            config (Dict[str, Any], optional): Configuration to override defaults.
        """
        self.config = config or {}
        self._setup_envelope_constants()
        self._setup_material_constants()
        self._setup_physical_constants()

    def _setup_envelope_constants(self) -> None:
        """Setup envelope equation constants."""
        envelope_config = self.config.get("envelope_equation", {})

        # Base stiffness coefficient κ₀ (dimensionless)
        self.KAPPA_0 = envelope_config.get("kappa_0", 1.0)

        # Nonlinear stiffness coefficient κ₂ (dimensionless)
        self.KAPPA_2 = envelope_config.get("kappa_2", 0.1)

        # Real part of susceptibility χ' (dimensionless)
        self.CHI_PRIME = envelope_config.get("chi_prime", 1.0)

        # Base imaginary susceptibility χ''₀ (dimensionless)
        self.CHI_DOUBLE_PRIME_0 = envelope_config.get("chi_double_prime_0", 0.01)

        # Wave number squared k₀² (1/m²)
        self.K0_SQUARED = envelope_config.get("k0_squared", 1.0)

        # Carrier frequency ω₀ (rad/s)
        self.CARRIER_FREQUENCY = envelope_config.get("carrier_frequency", 1.85e43)

        # BVP postulate parameters
        self.PHASE_VELOCITY_THRESHOLD = envelope_config.get(
            "phase_velocity_threshold", 1e6
        )
        self.EPSILON_THRESHOLD = envelope_config.get("epsilon_threshold", 0.1)

        # Quench detection thresholds
        self.AMPLITUDE_THRESHOLD = envelope_config.get("amplitude_threshold", 0.8)
        self.DETUNING_THRESHOLD = envelope_config.get("detuning_threshold", 0.1)
        self.GRADIENT_THRESHOLD = envelope_config.get("gradient_threshold", 0.5)

    def _setup_material_constants(self) -> None:
        """Setup material property constants with frequency-dependent models."""
        material_config = self.config.get("material_properties", {})

        # Backward-compat baseline values (deprecated as final values)
        self.EM_CONDUCTIVITY = material_config.get("em_conductivity", 0.01)
        self.WEAK_CONDUCTIVITY = material_config.get("weak_conductivity", 0.001)
        self.BASE_ADMITTANCE = material_config.get("base_admittance", 1.0)

        # Frequency-dependent model parameters (preferred path)
        self.BASE_CONDUCTIVITY = material_config.get(
            "base_conductivity", self.EM_CONDUCTIVITY
        )
        self.CUTOFF_FREQUENCY = material_config.get("cutoff_frequency", 1.0)
        self.ADMITTANCE_MODEL = material_config.get("admittance_model", "drude")
        self.MATERIAL_PARAMETERS = material_config.get("parameters", {})

        # U(1)^3 phase structure constants (unchanged)
        self.PHASE_AMPLITUDE_1 = material_config.get("phase_amplitude_1", 1.0)
        self.PHASE_AMPLITUDE_2 = material_config.get("phase_amplitude_2", 1.0)
        self.PHASE_AMPLITUDE_3 = material_config.get("phase_amplitude_3", 1.0)
        self.PHASE_FREQUENCY_1 = material_config.get("phase_frequency_1", 1.0)
        self.PHASE_FREQUENCY_2 = material_config.get("phase_frequency_2", 1.0)
        self.PHASE_FREQUENCY_3 = material_config.get("phase_frequency_3", 1.0)

        # SU(2) and electroweak couplings
        self.SU2_COUPLING_STRENGTH = material_config.get("su2_coupling_strength", 0.1)
        self.EM_COUPLING = material_config.get("em_coupling", 1.0)
        self.WEAK_COUPLING = material_config.get("weak_coupling", 0.1)
        self.MIXING_ANGLE = material_config.get("mixing_angle", 0.23)
        self.GAUGE_COUPLING = material_config.get("gauge_coupling", 0.65)

        # Basic material properties for fractional Laplacian
        self.MU = material_config.get("mu", 1.0)
        self.BETA = material_config.get("beta", 1.5)
        self.LAMBDA_PARAM = material_config.get("lambda_param", 0.1)
        self.NU = material_config.get("nu", 1.0)

    def get_conductivity(self, frequency: float) -> float:
        """Compute frequency-dependent conductivity σ(ω)."""
        if frequency < 0:
            frequency = abs(frequency)
        # Simple Drude-like model as default
        if self.ADMITTANCE_MODEL.lower() == "drude":
            gamma = float(self.MATERIAL_PARAMETERS.get("gamma", 0.0))
            omega_p = float(self.MATERIAL_PARAMETERS.get("omega_p", 0.0))
            omega = float(frequency)
            denom = gamma**2 + omega**2 if (gamma != 0.0 or omega != 0.0) else 1.0
            sigma = self.BASE_CONDUCTIVITY + (omega_p**2) * gamma / denom
            return float(sigma)
        if self.ADMITTANCE_MODEL.lower() == "debye":
            tau = float(self.MATERIAL_PARAMETERS.get("tau", 1.0))
            sigma_inf = float(
                self.MATERIAL_PARAMETERS.get("sigma_inf", self.BASE_CONDUCTIVITY)
            )
            omega = float(frequency)
            return float(sigma_inf * (1.0 / (1.0 + (omega * tau) ** 2)))
        # Fallback: quadratic correction using cutoff frequency
        return float(
            self.BASE_CONDUCTIVITY
            * (1.0 + (frequency**2) / max(self.CUTOFF_FREQUENCY, 1e-12) ** 2)
        )

    def get_admittance(self, frequency: float) -> float:
        """Compute frequency-dependent base admittance Y(ω)."""
        # Simple proportional relation to conductivity for baseline
        sigma = self.get_conductivity(frequency)
        return float(
            self.BASE_ADMITTANCE * (sigma / max(self.BASE_CONDUCTIVITY, 1e-30))
        )

    def _setup_physical_constants(self) -> None:
        """Setup fundamental physical constants."""
        physical_config = self.config.get("physical_constants", {})

        # Speed of light (m/s)
        self.SPEED_OF_LIGHT = physical_config.get("speed_of_light", 299792458.0)

        # Vacuum permeability (H/m)
        self.VACUUM_PERMEABILITY = physical_config.get(
            "vacuum_permeability", 4e-7 * np.pi
        )

        # Vacuum permittivity (F/m)
        self.VACUUM_PERMITTIVITY = physical_config.get(
            "vacuum_permittivity", 8.854187817e-12
        )

        # Planck constant (J⋅s)
        self.PLANCK_CONSTANT = physical_config.get("planck_constant", 6.62607015e-34)

        # Boltzmann constant (J/K)
        self.BOLTZMANN_CONSTANT = physical_config.get(
            "boltzmann_constant", 1.380649e-23
        )

    def get_envelope_parameter(self, parameter_name: str) -> float:
        """
        Get envelope equation parameter.

        Args:
            parameter_name (str): Name of the parameter.

        Returns:
            float: Parameter value.
        """
        parameter_map = {
            "kappa_0": self.KAPPA_0,
            "kappa_2": self.KAPPA_2,
            "chi_prime": self.CHI_PRIME,
            "chi_double_prime_0": self.CHI_DOUBLE_PRIME_0,
            "k0_squared": self.K0_SQUARED,
            "carrier_frequency": self.CARRIER_FREQUENCY,
        }
        return float(parameter_map.get(parameter_name, 0.0))

    def get_basic_material_property(self, property_name: str) -> float:
        """
        Get basic material property constant.

        Args:
            property_name (str): Name of the material property.

        Returns:
            float: Property value.
        """
        property_map = {
            "em_conductivity": self.EM_CONDUCTIVITY,
            "weak_conductivity": self.WEAK_CONDUCTIVITY,
            "base_admittance": self.BASE_ADMITTANCE,
            # U(1)³ phase structure properties
            "phase_amplitude_1": self.PHASE_AMPLITUDE_1,
            "phase_amplitude_2": self.PHASE_AMPLITUDE_2,
            "phase_amplitude_3": self.PHASE_AMPLITUDE_3,
            "phase_frequency_1": self.PHASE_FREQUENCY_1,
            "phase_frequency_2": self.PHASE_FREQUENCY_2,
            "phase_frequency_3": self.PHASE_FREQUENCY_3,
            "su2_coupling_strength": self.SU2_COUPLING_STRENGTH,
            # Electroweak properties
            "em_coupling": self.EM_COUPLING,
            "weak_coupling": self.WEAK_COUPLING,
            "mixing_angle": self.MIXING_ANGLE,
            "gauge_coupling": self.GAUGE_COUPLING,
            # Basic material properties for fractional Laplacian
            "mu": self.MU,
            "beta": self.BETA,
            "lambda_param": self.LAMBDA_PARAM,
            "nu": self.NU,
        }
        return float(property_map.get(property_name, 0.0))

    def get_physical_constant(self, constant_name: str) -> float:
        """
        Get fundamental physical constant.

        Args:
            constant_name (str): Name of the physical constant.

        Returns:
            float: Constant value.
        """
        constant_map = {
            "speed_of_light": self.SPEED_OF_LIGHT,
            "vacuum_permeability": self.VACUUM_PERMEABILITY,
            "vacuum_permittivity": self.VACUUM_PERMITTIVITY,
            "planck_constant": self.PLANCK_CONSTANT,
            "boltzmann_constant": self.BOLTZMANN_CONSTANT,
        }
        return float(constant_map.get(constant_name, 0.0))

    def get_physical_parameter(self, parameter_name: str) -> float:
        """
        Get physical parameter value.

        Physical Meaning:
            Retrieves physical parameters used in BVP postulates and calculations.

        Args:
            parameter_name (str): Name of the physical parameter.

        Returns:
            float: Physical parameter value.
        """
        parameter_map = {
            "carrier_frequency": self.CARRIER_FREQUENCY,
            "phase_velocity_threshold": self.PHASE_VELOCITY_THRESHOLD,
            "epsilon_threshold": self.EPSILON_THRESHOLD,
        }
        return float(parameter_map.get(parameter_name, 0.0))

    def get_carrier_frequency(self) -> float:
        """
        Get BVP carrier frequency.

        Physical Meaning:
            Returns the high-frequency carrier frequency ω₀ of the BVP field,
            which is the fundamental frequency that all envelope modulations
            and beatings are based upon.

        Returns:
            float: BVP carrier frequency ω₀.
        """
        return self.CARRIER_FREQUENCY

    def get_quench_parameter(self, parameter_name: str) -> float:
        """
        Get quench detection parameter value.

        Physical Meaning:
            Retrieves parameters used for quench detection in BVP postulates.

        Args:
            parameter_name (str): Name of the quench parameter.

        Returns:
            float: Quench parameter value.
        """
        quench_map = {
            "amplitude_threshold": self.AMPLITUDE_THRESHOLD,
            "detuning_threshold": self.DETUNING_THRESHOLD,
            "gradient_threshold": self.GRADIENT_THRESHOLD,
        }
        return float(quench_map.get(parameter_name, 0.0))

    def __repr__(self) -> str:
        """String representation of base BVP constants."""
        return (
            f"BVPConstantsBase(carrier_freq={self.CARRIER_FREQUENCY}, "
            f"kappa_0={self.KAPPA_0}, kappa_2={self.KAPPA_2})"
        )
