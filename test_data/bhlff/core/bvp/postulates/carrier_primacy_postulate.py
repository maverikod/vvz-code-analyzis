"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Postulate 1: Carrier Primacy implementation.

This module implements the Carrier Primacy postulate for the BVP framework,
validating that the real configuration consists of modulations of a
high-frequency carrier field.

Physical Meaning:
    The Carrier Primacy postulate states that all observed "modes" are
    envelope modulations and beatings of the Base High-Frequency Field (BVP).
    The real field configuration is fundamentally a high-frequency carrier
    with slow envelope modulations.

Mathematical Foundation:
    Validates that the field can be decomposed as:
    a(x,φ,t) = A(x,φ,t) * exp(iω₀t) + c.c.
    where A(x,φ,t) is the envelope and ω₀ is the carrier frequency.
    The postulate ensures that the carrier frequency dominates the spectrum
    and that envelope modulations are much slower than the carrier.

Example:
    >>> postulate = BVPPostulate1_CarrierPrimacy(domain_7d, config)
    >>> results = postulate.apply(envelope_7d)
    >>> print(f"Carrier primacy satisfied: {results['postulate_satisfied']}")
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_postulate_base import BVPPostulate


class BVPPostulate1_CarrierPrimacy(BVPPostulate):
    """
    Postulate 1: Carrier Primacy.

    Physical Meaning:
        Real configuration is modulations of high-frequency carrier (BVP).
        All observed "modes" are its envelopes and beatings.

    Mathematical Foundation:
        Validates that the field can be decomposed as:
        a(x,φ,t) = A(x,φ,t) * exp(iω₀t) + c.c.
        where A(x,φ,t) is the envelope and ω₀ is the carrier frequency.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize Carrier Primacy postulate.

        Physical Meaning:
            Sets up the postulate with the computational domain and
            configuration parameters, including the expected carrier frequency.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - carrier_frequency (float): Expected carrier frequency (default: 1.85e43)
        """
        self.domain_7d = domain_7d
        self.config = config
        self.carrier_frequency = config.get("carrier_frequency", 1.85e43)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply Carrier Primacy postulate.

        Physical Meaning:
            Validates that the field exhibits carrier primacy by checking
            that the envelope modulation is much slower than the carrier frequency.
            This ensures that the field is fundamentally a high-frequency carrier
            with slow envelope modulations, not a collection of independent modes.

        Mathematical Foundation:
            Computes the temporal power spectrum and identifies the dominant
            frequency component. Validates that this frequency matches the
            expected carrier frequency within tolerance.

        Args:
            envelope (np.ndarray): 7D envelope field to validate.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results including:
                - postulate_satisfied (bool): Whether postulate is satisfied
                - carrier_frequency (float): Detected carrier frequency
                - modulation_ratio (float): Ratio of modulation to carrier frequency
                - frequency_tolerance (float): Applied frequency tolerance
        """
        # Compute temporal FFT to find carrier frequency
        temporal_fft = np.fft.fft(envelope, axis=-1)
        temporal_freqs = np.fft.fftfreq(
            self.domain_7d.temporal_config.N_t, self.domain_7d.temporal_config.dt
        )

        # Find dominant frequency
        power_spectrum = np.abs(temporal_fft) ** 2
        total_power = np.sum(power_spectrum, axis=tuple(range(power_spectrum.ndim - 1)))
        dominant_freq_idx = np.argmax(total_power)
        detected_carrier_freq = np.abs(temporal_freqs[dominant_freq_idx])

        # Check if detected frequency matches expected carrier frequency
        frequency_tolerance = 0.1  # 10% tolerance
        frequency_match = (
            abs(detected_carrier_freq - self.carrier_frequency) / self.carrier_frequency
            < frequency_tolerance
        )

        # Compute modulation ratio
        modulation_ratio = detected_carrier_freq / self.carrier_frequency

        return {
            "postulate_satisfied": frequency_match,
            "carrier_frequency": float(detected_carrier_freq),
            "modulation_ratio": float(modulation_ratio),
            "frequency_tolerance": frequency_tolerance,
        }
