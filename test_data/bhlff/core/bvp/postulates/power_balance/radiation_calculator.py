"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radiation calculation for Power Balance Postulate.

This module implements radiation calculation methods for the Power Balance
Postulate, including EM/weak radiation losses and reflection calculations.

Theoretical Background:
    Radiation losses include electromagnetic and weak radiation from the
    envelope using full field theory. Reflection at boundaries is also
    calculated using electromagnetic theory.

Example:
    >>> radiation_calc = RadiationCalculator(domain, constants)
    >>> radiation_losses = radiation_calc.compute_radiation_losses(envelope)
    >>> reflection = radiation_calc.compute_reflection(envelope)
"""

import numpy as np
from typing import Dict, Any

from ....domain.domain import Domain
from ...bvp_constants import BVPConstants


class RadiationCalculator:
    """
    Radiation calculation for Power Balance Postulate.

    Physical Meaning:
        Calculates energy losses due to electromagnetic and weak radiation
        from the envelope using full field theory, and reflection at boundaries.

    Mathematical Foundation:
        Radiation losses include:
        - EM radiation: P_EM = σ_EM * |A|² * ω² / (8π²c²)
        - Weak radiation: P_weak = σ_weak * |A|⁴ * ω⁴ / (16π⁴c⁴)
        - Reflection: R = |(Z_L - Z_0)/(Z_L + Z_0)|²
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize radiation calculator.

        Physical Meaning:
            Sets up the radiation calculator with domain and constants
            for radiation and reflection calculations.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants

    def compute_radiation_losses(self, envelope: np.ndarray) -> float:
        """
        Compute EM/weak radiation and losses.

        Physical Meaning:
            Calculates energy losses due to electromagnetic and
            weak radiation from the envelope using full field theory.

        Mathematical Foundation:
            Radiation losses include:
            - EM radiation: P_EM = σ_EM * |A|² * ω² / (8π²c²)
            - Weak radiation: P_weak = σ_weak * |A|⁴ * ω⁴ / (16π⁴c⁴)
            - Total: P_total = P_EM + P_weak

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: Radiation losses.
        """
        amplitude = np.abs(envelope)
        carrier_frequency = self.constants.get_physical_parameter("carrier_frequency")

        # Get material properties for radiation calculations
        em_conductivity = self.constants.get_basic_material_property("em_conductivity")
        weak_conductivity = self.constants.get_basic_material_property(
            "weak_conductivity"
        )
        speed_of_light = self.constants.get_physical_constant("speed_of_light")

        # Compute EM radiation losses using full electromagnetic theory
        # P_EM = σ_EM * |A|² * ω² / (8π²c²)
        omega = 2 * np.pi * carrier_frequency
        em_radiation_losses = (
            em_conductivity
            * np.mean(amplitude**2)
            * omega**2
            / (8 * np.pi**2 * speed_of_light**2)
        )

        # Compute weak radiation losses using weak interaction theory
        # P_weak = σ_weak * |A|⁴ * ω⁴ / (16π⁴c⁴)
        weak_radiation_losses = (
            weak_conductivity
            * np.mean(amplitude**4)
            * omega**4
            / (16 * np.pi**4 * speed_of_light**4)
        )

        # Total radiation losses
        total_radiation_losses = em_radiation_losses + weak_radiation_losses

        return total_radiation_losses

    def compute_reflection(self, envelope: np.ndarray) -> float:
        """
        Compute reflection at boundaries.

        Physical Meaning:
            Calculates energy reflection at boundaries due to
            impedance mismatch using full electromagnetic theory.

        Mathematical Foundation:
            Reflection coefficient: R = |(Z_L - Z_0)/(Z_L + Z_0)|²
            where Z_L is load impedance and Z_0 is characteristic impedance.
            Reflected power: P_reflected = R * P_incident

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: Reflected energy.
        """
        amplitude = np.abs(envelope)

        # Compute impedance mismatch from envelope properties
        # Characteristic impedance Z_0 from material properties
        vacuum_permeability = self.constants.get_physical_constant(
            "vacuum_permeability"
        )
        vacuum_permittivity = self.constants.get_physical_constant(
            "vacuum_permittivity"
        )
        z0_characteristic = np.sqrt(vacuum_permeability / vacuum_permittivity)

        # Load impedance Z_L from envelope admittance
        # Z_L = 1/Y where Y is admittance from envelope
        envelope_admittance = self._compute_envelope_admittance(envelope)
        zl_load = 1.0 / (envelope_admittance + 1e-12)  # Avoid division by zero

        # Compute reflection coefficient using full electromagnetic theory
        # R = |(Z_L - Z_0)/(Z_L + Z_0)|²
        reflection_coefficient = (
            np.abs((zl_load - z0_characteristic) / (zl_load + z0_characteristic)) ** 2
        )

        # Compute incident power from envelope amplitude
        incident_power = np.mean(amplitude**2)

        # Reflected power
        reflected_power = reflection_coefficient * incident_power

        return reflected_power

    def _compute_envelope_admittance(self, envelope: np.ndarray) -> float:
        """
        Compute envelope admittance from field properties.

        Physical Meaning:
            Calculates admittance from envelope gradient and amplitude
            using transmission line theory.

        Mathematical Foundation:
            Y = (1/Z) * (∇A/A) where A is envelope amplitude.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: Envelope admittance.
        """
        amplitude = np.abs(envelope)

        # Compute spatial gradient of amplitude
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)
        gradient_magnitude = np.abs(gradient)

        # Compute admittance from gradient-to-amplitude ratio
        # Y = (1/Z) * (∇A/A) where Z is characteristic impedance
        vacuum_permeability = self.constants.get_physical_constant(
            "vacuum_permeability"
        )
        vacuum_permittivity = self.constants.get_physical_constant(
            "vacuum_permittivity"
        )
        z_characteristic = np.sqrt(vacuum_permeability / vacuum_permittivity)

        # Average admittance over the domain
        admittance = (
            np.mean(gradient_magnitude / (amplitude + 1e-12)) / z_characteristic
        )

        return admittance
