"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Nonlinear coefficients computation for envelope equation.

This module implements the computation of nonlinear coefficients
κ(|a|) and χ(|a|) as functions of field amplitude according to
the BVP theoretical framework, replacing static parameters with
adaptive nonlinear behavior.

Physical Meaning:
    Computes nonlinear stiffness κ(|a|) and susceptibility χ(|a|)
    as functions of the local field amplitude, ensuring proper
    nonlinear behavior according to the envelope equation.

Mathematical Foundation:
    κ(|a|) = κ₀ + κ₂|a|²
    χ(|a|) = χ' + iχ''(|a|)
    where coefficients depend on local field properties.

Example:
    >>> coeffs = EnvelopeNonlinearCoefficients(constants)
    >>> nonlinear_coeffs = coeffs.compute_coefficients(envelope)
    >>> print(f"Kappa range: {np.min(nonlinear_coeffs['kappa'])} - {np.max(nonlinear_coeffs['kappa'])}")
"""

import numpy as np
from typing import Dict, Any

from .bvp_constants import BVPConstants
from .memory_decorator import memory_protected_class_method


class EnvelopeNonlinearCoefficients:
    """
    Computer for nonlinear coefficients in envelope equation.

    Physical Meaning:
        Computes nonlinear stiffness κ(|a|) and susceptibility χ(|a|)
        as functions of the local field amplitude, ensuring proper
        nonlinear behavior according to the envelope equation.

    Mathematical Foundation:
        κ(|a|) = κ₀ + κ₂|a|²
        χ(|a|) = χ' + iχ''(|a|)
        where coefficients depend on local field properties.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize nonlinear coefficients computer.

        Physical Meaning:
            Sets up the coefficients computer with the BVP constants
            to compute nonlinear coefficients based on theoretical
            framework parameters.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants

        # Base parameters for nonlinear coefficient computation
        self.kappa_0 = constants.get_envelope_parameter("kappa_0")
        self.kappa_2 = constants.get_envelope_parameter("kappa_2")
        self.chi_prime = constants.get_envelope_parameter("chi_prime")
        self.chi_double_prime_0 = constants.get_envelope_parameter("chi_double_prime_0")

        # Nonlinear coefficient computation parameters
        try:
            self.nonlinear_threshold = constants.get_envelope_parameter(
                "nonlinear_threshold"
            )
        except KeyError:
            self.nonlinear_threshold = 0.1

        try:
            self.adaptive_scaling = constants.get_envelope_parameter("adaptive_scaling")
        except KeyError:
            self.adaptive_scaling = True

    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="envelope", dtype_param="envelope"
    )
    def compute_coefficients(self, envelope: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compute nonlinear coefficients as functions of field amplitude.

        Physical Meaning:
            Computes the nonlinear stiffness κ(|a|) and susceptibility χ(|a|)
            as functions of the local field amplitude, ensuring proper
            nonlinear behavior according to the envelope equation.

        Mathematical Foundation:
            κ(|a|) = κ₀ + κ₂|a|²
            χ(|a|) = χ' + iχ''(|a|)
            where coefficients depend on local field properties.

        Args:
            envelope (np.ndarray): Current envelope field a(x,φ,t).

        Returns:
            Dict[str, np.ndarray]: Dictionary containing:
                - kappa: Nonlinear stiffness κ(|a|)
                - chi_real: Real part of susceptibility χ'(|a|)
                - chi_imag: Imaginary part of susceptibility χ''(|a|)
        """
        amplitude = np.abs(envelope)

        # Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|²
        kappa = self.kappa_0 + self.kappa_2 * amplitude**2

        # Compute nonlinear susceptibility χ(|a|) = χ' + iχ''(|a|)
        chi_real = self.chi_prime + self._compute_chi_real_nonlinear(amplitude)
        chi_imag = self.chi_double_prime_0 + self._compute_chi_imag_nonlinear(amplitude)

        return {"kappa": kappa, "chi_real": chi_real, "chi_imag": chi_imag}

    def _compute_chi_real_nonlinear(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear real part of susceptibility.

        Physical Meaning:
            Computes the nonlinear contribution to the real part of
            susceptibility based on field amplitude, representing
            dispersive nonlinear effects.

        Mathematical Foundation:
            χ'_nl(|a|) = α₁|a|² + α₂|a|⁴ + ...
            where αᵢ are nonlinear coefficients from the theoretical framework.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Nonlinear real susceptibility χ'_nl(|a|).
        """
        # Nonlinear coefficients from theoretical framework
        try:
            alpha_1 = self.constants.get_envelope_parameter("chi_real_nonlinear_1")
        except KeyError:
            alpha_1 = 0.1

        try:
            alpha_2 = self.constants.get_envelope_parameter("chi_real_nonlinear_2")
        except KeyError:
            alpha_2 = 0.01

        # Compute nonlinear contribution
        chi_real_nl = alpha_1 * amplitude**2 + alpha_2 * amplitude**4

        # Apply adaptive scaling if enabled
        if self.adaptive_scaling:
            # Scale based on local field properties
            local_scale = self._compute_local_adaptive_scale(amplitude)
            chi_real_nl *= local_scale

        return chi_real_nl

    def _compute_chi_imag_nonlinear(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear imaginary part of susceptibility.

        Physical Meaning:
            Computes the nonlinear contribution to the imaginary part of
            susceptibility based on field amplitude, representing
            absorptive nonlinear effects.

        Mathematical Foundation:
            χ''_nl(|a|) = β₁|a|² + β₂|a|⁴ + ...
            where βᵢ are nonlinear coefficients from the theoretical framework.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Nonlinear imaginary susceptibility χ''_nl(|a|).
        """
        # Nonlinear coefficients from theoretical framework
        try:
            beta_1 = self.constants.get_envelope_parameter("chi_imag_nonlinear_1")
        except KeyError:
            beta_1 = 0.05

        try:
            beta_2 = self.constants.get_envelope_parameter("chi_imag_nonlinear_2")
        except KeyError:
            beta_2 = 0.005

        # Compute nonlinear contribution
        chi_imag_nl = beta_1 * amplitude**2 + beta_2 * amplitude**4

        # Apply adaptive scaling if enabled
        if self.adaptive_scaling:
            # Scale based on local field properties
            local_scale = self._compute_local_adaptive_scale(amplitude)
            chi_imag_nl *= local_scale

        return chi_imag_nl

    def _compute_local_adaptive_scale(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute local adaptive scaling factor.

        Physical Meaning:
            Computes adaptive scaling factors based on local field properties
            to ensure proper nonlinear behavior in different regions of
            the 7D space-time.

        Mathematical Foundation:
            Scale factor depends on local field gradients, phase coherence,
            and energy density to adapt nonlinear coefficients to local conditions.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Local adaptive scaling factors.
        """
        # Compute local field properties
        amplitude_gradient = np.sqrt(
            sum(np.gradient(amplitude, axis=i) ** 2 for i in range(amplitude.ndim))
        )

        # Compute phase coherence (if complex field)
        if np.iscomplexobj(amplitude):
            phase = np.angle(amplitude)
            phase_gradient = np.sqrt(
                sum(np.gradient(phase, axis=i) ** 2 for i in range(phase.ndim))
            )
            coherence = 1.0 / (1.0 + phase_gradient)
        else:
            coherence = np.ones_like(amplitude)

        # Compute energy density
        energy_density = amplitude**2

        # Adaptive scaling based on local properties
        scale_factor = (
            coherence
            * (1.0 + self.nonlinear_threshold * energy_density)
            / (1.0 + amplitude_gradient)
        )

        # Ensure reasonable bounds
        scale_factor = np.clip(scale_factor, 0.1, 10.0)

        return scale_factor

    def get_base_parameters(self) -> Dict[str, float]:
        """
        Get base parameters for nonlinear coefficients.

        Physical Meaning:
            Returns the base parameters used for computing nonlinear
            coefficients, showing the theoretical framework parameters.

        Returns:
            Dict[str, float]: Base parameters for nonlinear coefficients.
        """
        return {
            "kappa_0": self.kappa_0,
            "kappa_2": self.kappa_2,
            "chi_prime": self.chi_prime,
            "chi_double_prime_0": self.chi_double_prime_0,
            "nonlinear_threshold": self.nonlinear_threshold,
            "adaptive_scaling": self.adaptive_scaling,
        }
