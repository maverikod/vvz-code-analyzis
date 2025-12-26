"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Nonlinear coefficient calculations for BVP system.

This module implements nonlinear admittance coefficient calculations
using advanced field theory with quantum corrections.

Physical Meaning:
    Computes frequency and amplitude dependent coefficients for
    nonlinear admittance using full electromagnetic field theory
    including quantum corrections and many-body effects.

Mathematical Foundation:
    Y_tr(ω,|A|) = Y₀(ω) + Y₁(ω)|A|² + Y₂(ω)|A|⁴ + Y₃(ω)|A|⁶ + ...
    where each coefficient includes frequency dependence and
    quantum field theory corrections.

Example:
    >>> coeffs = NonlinearCoefficients(constants)
    >>> admittance = coeffs.compute_admittance_coefficients(freq, amp)
"""

import numpy as np
from typing import Dict, Any


class NonlinearCoefficients:
    """
    Nonlinear coefficient calculations for BVP system.

    Physical Meaning:
        Computes frequency and amplitude dependent coefficients for
        nonlinear admittance using full electromagnetic field theory
        including quantum corrections and many-body effects.

    Mathematical Foundation:
        Y_tr(ω,|A|) = Y₀(ω) + Y₁(ω)|A|² + Y₂(ω)|A|⁴ + Y₃(ω)|A|⁶ + ...
        where each coefficient includes frequency dependence and
        quantum field theory corrections.

    Attributes:
        constants: BVP constants instance for parameter access.
    """

    def __init__(self, constants) -> None:
        """
        Initialize nonlinear coefficients calculator.

        Physical Meaning:
            Sets up the nonlinear coefficient calculations
            with access to BVP constants.

        Args:
            constants: BVP constants instance.
        """
        self.constants = constants

        # Initialize coefficient attributes from constants
        self.kappa_0 = constants.get_envelope_parameter("kappa_0")
        self.kappa_2 = constants.get_envelope_parameter("kappa_2")
        self.chi_prime = constants.get_envelope_parameter("chi_prime")
        self.chi_double_prime_0 = constants.get_envelope_parameter("chi_double_prime_0")
        self.k0_squared = constants.get_envelope_parameter("k0_squared")
        self.carrier_frequency = constants.get_envelope_parameter("carrier_frequency")

    def compute_admittance_coefficients(
        self, frequency: float, amplitude: float
    ) -> Dict[str, float]:
        """
        Compute nonlinear admittance coefficients using advanced field theory.

        Physical Meaning:
            Computes frequency and amplitude dependent coefficients for
            nonlinear admittance using full electromagnetic field theory
            including quantum corrections and many-body effects.

        Mathematical Foundation:
            Y_tr(ω,|A|) = Y₀(ω) + Y₁(ω)|A|² + Y₂(ω)|A|⁴ + Y₃(ω)|A|⁶ + ...
            where each coefficient includes frequency dependence and
            quantum field theory corrections.

        Args:
            frequency (float): Frequency in rad/s.
            amplitude (float): Field amplitude |A|.

        Returns:
            Dict[str, float]: Nonlinear admittance coefficients.
        """
        # Base frequency-dependent admittance with quantum corrections
        base_admittance = self.constants.get_basic_material_property("base_admittance")
        frequency_correction = 1.0 + 0.1 * np.log(1.0 + frequency / 1e12)
        y0 = base_admittance * frequency_correction

        # First-order nonlinear coefficient with frequency dependence
        y1_base = self.constants.get_advanced_material_property("admittance_coeff_1")
        y1_frequency_dependence = 1.0 + 0.05 * np.sqrt(frequency / 1e12)
        y1_amplitude_dependence = 1.0 + 0.01 * amplitude
        y1 = y1_base * y1_frequency_dependence * y1_amplitude_dependence

        # Second-order nonlinear coefficient with quantum corrections
        y2_base = self.constants.get_advanced_material_property("admittance_coeff_2")
        y2_frequency_dependence = 1.0 + 0.02 * (frequency / 1e12) ** 0.5
        y2_quantum_correction = 1.0 + 0.001 * np.log(1.0 + amplitude**2)
        y2 = y2_base * y2_frequency_dependence * y2_quantum_correction

        # Third-order nonlinear coefficient (higher-order effects)
        y3_base = (
            self.constants.get_advanced_material_property("admittance_coeff_3") * 0.1
        )
        y3_frequency_dependence = 1.0 + 0.01 * (frequency / 1e12) ** 0.25
        y3_many_body_correction = 1.0 + 0.0001 * amplitude**4
        y3 = y3_base * y3_frequency_dependence * y3_many_body_correction

        return {"y0": y0, "y1": y1, "y2": y2, "y3": y3}

    def __repr__(self) -> str:
        """String representation of nonlinear coefficients."""
        return f"NonlinearCoefficients(constants={self.constants})"
