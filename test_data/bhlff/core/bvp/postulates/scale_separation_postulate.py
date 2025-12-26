"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Postulate 2: Scale Separation implementation.

This module implements the Scale Separation postulate for the BVP framework,
validating that the scale separation parameter ε = Ω/ω₀ << 1 is satisfied
throughout the field.

Physical Meaning:
    The Scale Separation postulate ensures that there is a clear separation
    between the high-frequency carrier (ω₀) and the characteristic frequencies
    of envelope modulations and medium response (Ω). This separation is
    fundamental to the validity of the envelope approximation.

Mathematical Foundation:
    Validates that the scale separation parameter ε = Ω/ω₀ << 1 is satisfied
    throughout the field, where ω₀ is the BVP carrier frequency and Ω is the
    characteristic envelope/medium response frequency.

Example:
    >>> postulate = BVPPostulate2_ScaleSeparation(domain_7d, config)
    >>> results = postulate.apply(envelope_7d)
    >>> print(f"Scale separation satisfied: {results['postulate_satisfied']}")
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_postulate_base import BVPPostulate


class BVPPostulate2_ScaleSeparation(BVPPostulate):
    """
    Postulate 2: Scale Separation.

    Physical Meaning:
        Small parameter ε = Ω/ω₀ << 1 where ω₀ is BVP frequency and
        Ω is characteristic envelope/medium response frequencies.

    Mathematical Foundation:
        Validates that the scale separation parameter ε = Ω/ω₀ << 1
        is satisfied throughout the field.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize Scale Separation postulate.

        Physical Meaning:
            Sets up the postulate with the computational domain and
            configuration parameters, including the maximum allowed
            scale separation parameter ε.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - carrier_frequency (float): BVP carrier frequency (default: 1.85e43)
                - max_epsilon (float): Maximum allowed ε (default: 0.1)
        """
        self.domain_7d = domain_7d
        self.config = config
        self.carrier_frequency = config.get("carrier_frequency", 1.85e43)
        self.max_epsilon = config.get("max_epsilon", 0.1)  # Maximum allowed ε

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply Scale Separation postulate.

        Physical Meaning:
            Validates that the scale separation parameter ε = Ω/ω₀ << 1
            is satisfied by analyzing the frequency content of the envelope.
            This ensures that envelope modulations are much slower than
            the carrier frequency, validating the envelope approximation.

        Mathematical Foundation:
            Computes the characteristic envelope frequency Ω by analyzing
            the power spectrum of the envelope field. Validates that
            ε = Ω/ω₀ < max_epsilon throughout the field.

        Args:
            envelope (np.ndarray): 7D envelope field to validate.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results including:
                - postulate_satisfied (bool): Whether postulate is satisfied
                - max_epsilon (float): Maximum value of ε found
                - mean_epsilon (float): Mean value of ε
                - scale_separation_ratio (float): Ratio of envelope to carrier frequencies
                - characteristic_frequency (float): Characteristic envelope frequency Ω
                - max_allowed_epsilon (float): Maximum allowed ε value
        """
        # Compute envelope frequency content
        envelope_fft = np.fft.fftn(envelope)
        envelope_power = np.abs(envelope_fft) ** 2

        # Get frequency arrays
        spatial_freqs = [
            np.fft.fftfreq(n, d)
            for n, d in zip(
                self.domain_7d.spatial_shape,
                [
                    self.domain_7d.L_spatial / self.domain_7d.N_spatial,
                    self.domain_7d.L_spatial / self.domain_7d.N_spatial,
                    self.domain_7d.L_spatial / self.domain_7d.N_spatial,
                ],
            )
        ]

        # Compute characteristic envelope frequency Ω
        # Use the maximum frequency component with significant power
        max_power = np.max(envelope_power)
        significant_power_threshold = 0.01 * max_power

        # Find maximum frequency with significant power
        significant_indices = np.where(envelope_power > significant_power_threshold)
        if len(significant_indices[0]) > 0:
            max_freq_components = []
            for i, freq_array in enumerate(spatial_freqs):
                if i < len(significant_indices):
                    max_freq_components.append(
                        np.max(np.abs(freq_array[significant_indices[i]]))
                    )

            characteristic_frequency = np.sqrt(sum(f**2 for f in max_freq_components))
        else:
            characteristic_frequency = 0.0

        # Compute scale separation parameter ε = Ω/ω₀
        epsilon = characteristic_frequency / self.carrier_frequency

        # Check if scale separation is satisfied
        scale_separation_satisfied = epsilon < self.max_epsilon

        return {
            "postulate_satisfied": scale_separation_satisfied,
            "max_epsilon": float(np.max(epsilon) if np.isscalar(epsilon) else epsilon),
            "mean_epsilon": float(
                np.mean(epsilon) if np.isscalar(epsilon) else epsilon
            ),
            "scale_separation_ratio": float(epsilon),
            "characteristic_frequency": float(characteristic_frequency),
            "max_allowed_epsilon": self.max_epsilon,
        }
