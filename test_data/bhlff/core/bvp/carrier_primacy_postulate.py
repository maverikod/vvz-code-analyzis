"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Carrier Primacy Postulate implementation for BVP framework.

This module implements Postulate 1 of the BVP framework, which states that
the carrier frequency ω₀ is much higher than any envelope frequency ω_env,
and the envelope is a small modulation of the carrier.

Theoretical Background:
    The carrier frequency represents the fundamental BVP field oscillation,
    while envelope frequencies represent slow modulations. This postulate
    ensures scale separation between carrier and envelope dynamics.

Example:
    >>> postulate = CarrierPrimacyPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any
from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate


class CarrierPrimacyPostulate(BVPPostulate):
    """
    Postulate 1: Carrier Primacy.

    Physical Meaning:
        Carrier frequency ω₀ >> ω_env (any envelope frequency).
        Envelope is small modulation of carrier.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize carrier primacy postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            analyzing carrier-envelope scale separation.

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
        Apply carrier primacy postulate.

        Physical Meaning:
            Verifies that carrier frequency dominates over envelope
            frequencies and envelope represents small modulation.

        Mathematical Foundation:
            Analyzes frequency spectrum to ensure ω₀ >> ω_env
            and envelope amplitude is small compared to carrier.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including frequency analysis,
                scale separation, and modulation strength.
        """
        # Analyze frequency spectrum
        frequency_analysis = self._analyze_frequency_spectrum(envelope)

        # Check scale separation
        scale_separation = self._check_scale_separation(frequency_analysis)

        # Analyze modulation strength
        modulation_analysis = self._analyze_modulation_strength(envelope)

        # Validate carrier primacy
        satisfies_postulate = self._validate_carrier_primacy(
            scale_separation, modulation_analysis
        )

        return {
            "frequency_analysis": frequency_analysis,
            "scale_separation": scale_separation,
            "modulation_analysis": modulation_analysis,
            "satisfies_postulate": satisfies_postulate,
            "postulate_satisfied": satisfies_postulate,
        }

    def _analyze_frequency_spectrum(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze frequency spectrum of the envelope.

        Physical Meaning:
            Performs FFT analysis to identify dominant frequencies
            and their relative magnitudes.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Frequency spectrum analysis.
        """
        # FFT in temporal dimension
        temporal_fft = np.fft.fft(envelope, axis=6)
        spectrum = np.abs(temporal_fft)

        # Find dominant frequencies
        freq_axis = np.fft.fftfreq(envelope.shape[6], self.domain.dt)
        dominant_freqs = self._find_dominant_frequencies(spectrum, freq_axis)

        # Compute frequency statistics
        freq_stats = self._compute_frequency_statistics(spectrum, freq_axis)

        return {
            "spectrum": spectrum,
            "frequencies": freq_axis,
            "dominant_frequencies": dominant_freqs,
            "statistics": freq_stats,
        }

    def _find_dominant_frequencies(
        self, spectrum: np.ndarray, freq_axis: np.ndarray
    ) -> Dict[str, float]:
        """
        Find dominant frequencies in the spectrum.

        Physical Meaning:
            Identifies peaks in frequency spectrum that correspond
            to significant frequency components.

        Args:
            spectrum (np.ndarray): Frequency spectrum magnitude.
            freq_axis (np.ndarray): Frequency axis values.

        Returns:
            Dict[str, float]: Dominant frequency components.
        """
        # Find maximum amplitude frequency
        # Get the maximum along the temporal axis (axis 6)
        max_indices = np.unravel_index(np.argmax(spectrum), spectrum.shape)
        max_idx = max_indices[6]  # Get temporal index
        max_freq = freq_axis[max_idx]

        # Find envelope frequency (second highest peak)
        spectrum_copy = spectrum.copy()
        # Remove carrier peak in the temporal dimension
        spectrum_copy[..., max_idx] = 0
        envelope_indices = np.unravel_index(
            np.argmax(spectrum_copy), spectrum_copy.shape
        )
        envelope_idx = envelope_indices[6]  # Get temporal index

        # Ensure envelope_idx is within bounds
        if envelope_idx >= len(freq_axis):
            envelope_idx = len(freq_axis) - 1
        envelope_freq = freq_axis[envelope_idx]

        return {
            "carrier_frequency": max_freq,
            "envelope_frequency": envelope_freq,
            "frequency_ratio": abs(max_freq / (envelope_freq + 1e-12)),
        }

    def _compute_frequency_statistics(
        self, spectrum: np.ndarray, freq_axis: np.ndarray
    ) -> Dict[str, float]:
        """
        Compute frequency statistics.

        Physical Meaning:
            Calculates statistical measures of frequency distribution
            to characterize spectrum properties.

        Args:
            spectrum (np.ndarray): Frequency spectrum magnitude.
            freq_axis (np.ndarray): Frequency axis values.

        Returns:
            Dict[str, float]: Frequency statistics.
        """
        # Compute weighted statistics
        total_power = np.sum(spectrum)
        mean_freq = np.sum(spectrum * freq_axis) / total_power
        freq_variance = np.sum(spectrum * (freq_axis - mean_freq) ** 2) / total_power

        return {
            "total_power": total_power,
            "mean_frequency": mean_freq,
            "frequency_variance": freq_variance,
            "frequency_std": np.sqrt(freq_variance),
        }

    def _check_scale_separation(
        self, frequency_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check scale separation between carrier and envelope.

        Physical Meaning:
            Verifies that carrier frequency is much higher than
            envelope frequencies, ensuring proper scale separation.

        Args:
            frequency_analysis (Dict[str, Any]): Frequency analysis results.

        Returns:
            Dict[str, Any]: Scale separation analysis.
        """
        dominant_freqs = frequency_analysis["dominant_frequencies"]
        carrier_freq = dominant_freqs["carrier_frequency"]
        envelope_freq = dominant_freqs["envelope_frequency"]
        frequency_ratio = dominant_freqs["frequency_ratio"]

        # Check if scale separation is sufficient
        sufficient_separation = frequency_ratio > self.scale_separation_threshold

        return {
            "carrier_frequency": carrier_freq,
            "envelope_frequency": envelope_freq,
            "frequency_ratio": frequency_ratio,
            "sufficient_separation": sufficient_separation,
            "separation_quality": min(
                frequency_ratio / max(self.scale_separation_threshold, 1e-12), 1.0
            ),
        }

    def _analyze_modulation_strength(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze modulation strength of the envelope.

        Physical Meaning:
            Quantifies how small the envelope modulation is
            compared to the carrier amplitude.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Modulation strength analysis.
        """
        amplitude = np.abs(envelope)

        # Compute modulation statistics
        mean_amplitude = np.mean(amplitude)
        amplitude_std = np.std(amplitude)
        modulation_index = amplitude_std / (mean_amplitude + 1e-12)

        # Check if modulation is small
        small_modulation = modulation_index < 0.1  # 10% modulation threshold

        return {
            "mean_amplitude": mean_amplitude,
            "amplitude_std": amplitude_std,
            "modulation_index": modulation_index,
            "small_modulation": small_modulation,
            "modulation_quality": max(0.1 - modulation_index, 0.0) / 0.1,
        }

    def _validate_carrier_primacy(
        self, scale_separation: Dict[str, Any], modulation_analysis: Dict[str, Any]
    ) -> bool:
        """
        Validate carrier primacy postulate.

        Physical Meaning:
            Checks that both scale separation and small modulation
            conditions are satisfied.

        Args:
            scale_separation (Dict[str, Any]): Scale separation analysis.
            modulation_analysis (Dict[str, Any]): Modulation analysis.

        Returns:
            bool: True if carrier primacy is satisfied.
        """
        sufficient_separation = scale_separation["sufficient_separation"]
        small_modulation = modulation_analysis["small_modulation"]

        return sufficient_separation and small_modulation
