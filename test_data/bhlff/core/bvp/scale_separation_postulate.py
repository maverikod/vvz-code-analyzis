"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scale Separation Postulate implementation for BVP framework.

This module implements Postulate 2 of the BVP framework, which states that
envelope length scale ℓ >> λ₀ (carrier wavelength), ensuring proper
scale separation between envelope and carrier dynamics.

Theoretical Background:
    The envelope length scale must be much larger than the carrier wavelength
    to ensure that envelope dynamics are slow compared to carrier oscillations.
    This separation is essential for the validity of envelope approximation.

Example:
    >>> postulate = ScaleSeparationPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any
from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate


class ScaleSeparationPostulate(BVPPostulate):
    """
    Postulate 2: Scale Separation.

    Physical Meaning:
        Envelope length scale ℓ >> λ₀ (carrier wavelength).
        Ensures proper scale separation between envelope and carrier.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize scale separation postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            analyzing length scale separation.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.carrier_frequency = constants.get_physical_parameter("carrier_frequency")
        self.scale_separation_threshold = constants.get_quench_parameter(
            "scale_separation_threshold"
        )

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply scale separation postulate.

        Physical Meaning:
            Verifies that envelope length scale is much larger than
            carrier wavelength, ensuring proper scale separation.

        Mathematical Foundation:
            Analyzes spatial gradients to determine envelope length
            scale and compares with carrier wavelength.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including length scale analysis,
                wavelength comparison, and separation validation.
        """
        # Analyze envelope length scale
        length_scale_analysis = self._analyze_envelope_length_scale(envelope)

        # Compute carrier wavelength
        carrier_wavelength = self._compute_carrier_wavelength()

        # Check scale separation
        scale_separation = self._check_scale_separation(
            length_scale_analysis, carrier_wavelength
        )

        # Validate scale separation
        satisfies_postulate = self._validate_scale_separation(scale_separation)

        return {
            "length_scale_analysis": length_scale_analysis,
            "carrier_wavelength": carrier_wavelength,
            "scale_separation": scale_separation,
            "satisfies_postulate": satisfies_postulate,
            "postulate_satisfied": satisfies_postulate,
        }

    def _analyze_envelope_length_scale(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze envelope length scale from spatial gradients.

        Physical Meaning:
            Computes characteristic length scale of envelope variations
            from spatial gradient analysis.

        Mathematical Foundation:
            Length scale ℓ ≈ |A|/|∇A| where A is envelope amplitude.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Length scale analysis.
        """
        amplitude = np.abs(envelope)

        # Compute spatial gradients
        gradients = []
        for axis in range(3):  # Spatial dimensions only
            gradient = np.gradient(amplitude, self.domain.dx, axis=axis)
            gradients.append(gradient)

        # Compute gradient magnitude
        gradient_magnitude = np.sqrt(sum(g**2 for g in gradients))

        # Compute length scale
        length_scale = amplitude / (gradient_magnitude + 1e-12)

        # Compute statistics
        mean_length_scale = np.mean(length_scale)
        std_length_scale = np.std(length_scale)
        min_length_scale = np.min(length_scale)
        max_length_scale = np.max(length_scale)

        return {
            "length_scale_field": length_scale,
            "mean_length_scale": mean_length_scale,
            "std_length_scale": std_length_scale,
            "min_length_scale": min_length_scale,
            "max_length_scale": max_length_scale,
            "gradient_magnitude": gradient_magnitude,
        }

    def _compute_carrier_wavelength(self) -> float:
        """
        Compute carrier wavelength.

        Physical Meaning:
            Calculates carrier wavelength from carrier frequency
            and propagation speed.

        Mathematical Foundation:
            λ₀ = 2πc/ω₀ where c is propagation speed and ω₀ is carrier frequency.

        Returns:
            float: Carrier wavelength.
        """
        # Assume propagation speed is unity for BVP field
        propagation_speed = 1.0
        carrier_wavelength = 2 * np.pi * propagation_speed / self.carrier_frequency

        return carrier_wavelength

    def _check_scale_separation(
        self, length_scale_analysis: Dict[str, Any], carrier_wavelength: float
    ) -> Dict[str, Any]:
        """
        Check scale separation between envelope and carrier.

        Physical Meaning:
            Verifies that envelope length scale is much larger than
            carrier wavelength.

        Args:
            length_scale_analysis (Dict[str, Any]): Length scale analysis.
            carrier_wavelength (float): Carrier wavelength.

        Returns:
            Dict[str, Any]: Scale separation analysis.
        """
        mean_length_scale = length_scale_analysis["mean_length_scale"]
        min_length_scale = length_scale_analysis["min_length_scale"]

        # Compute scale ratios
        mean_scale_ratio = mean_length_scale / carrier_wavelength
        min_scale_ratio = min_length_scale / carrier_wavelength

        # Check if separation is sufficient
        sufficient_separation = min_scale_ratio > self.scale_separation_threshold

        return {
            "mean_scale_ratio": mean_scale_ratio,
            "min_scale_ratio": min_scale_ratio,
            "sufficient_separation": sufficient_separation,
            "separation_quality": min(
                min_scale_ratio / max(self.scale_separation_threshold, 1e-12), 1.0
            ),
        }

    def _validate_scale_separation(self, scale_separation: Dict[str, Any]) -> bool:
        """
        Validate scale separation postulate.

        Physical Meaning:
            Checks that scale separation is sufficient for envelope
            approximation validity.

        Args:
            scale_separation (Dict[str, Any]): Scale separation analysis.

        Returns:
            bool: True if scale separation is satisfied.
        """
        return scale_separation["sufficient_separation"]
