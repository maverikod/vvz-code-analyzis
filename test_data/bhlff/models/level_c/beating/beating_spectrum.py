"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating spectrum analysis utilities for Level C.

This module implements spectrum analysis functions for beating
analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore


class BeatingSpectrumAnalyzer:
    """
    Spectrum analysis utilities for beating analysis.

    Physical Meaning:
        Provides spectrum analysis functions for beating analysis,
        including frequency analysis, pattern detection, and
        statistical analysis of mode interactions.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating spectrum analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def calculate_beating_spectrum(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate beating spectrum from envelope field.

        Physical Meaning:
            Calculates the beating spectrum by analyzing frequency
            differences and interference patterns in the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Beating spectrum analysis results.
        """
        self.logger.info("Calculating beating spectrum")

        # Calculate frequency spectrum
        frequency_spectrum = self._calculate_frequency_spectrum(envelope)

        # Calculate beating frequencies
        beating_frequencies = self._calculate_beating_frequencies(frequency_spectrum)

        # Calculate interference patterns
        interference_patterns = self._calculate_interference_patterns(
            envelope, beating_frequencies
        )

        # Calculate spectrum statistics
        spectrum_stats = self._calculate_spectrum_statistics(
            frequency_spectrum, beating_frequencies
        )

        results = {
            "frequency_spectrum": frequency_spectrum,
            "beating_frequencies": beating_frequencies,
            "interference_patterns": interference_patterns,
            "spectrum_stats": spectrum_stats,
        }

        self.logger.info(
            f"Beating spectrum calculated. Found {len(beating_frequencies)} beating frequencies"
        )
        return results

    def _calculate_frequency_spectrum(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate frequency spectrum of the envelope field.

        Physical Meaning:
            Calculates the frequency spectrum using FFT analysis
            to identify dominant frequencies and their amplitudes.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency spectrum analysis results.
        """
        # Calculate FFT
        fft_result = np.fft.fftn(envelope)

        # Calculate frequency magnitudes
        frequency_magnitudes = np.abs(fft_result)

        # Find dominant frequencies
        dominant_frequencies = self._find_dominant_frequencies(frequency_magnitudes)

        # Calculate frequency statistics
        frequency_stats = self._calculate_frequency_statistics(frequency_magnitudes)

        return {
            "fft_result": fft_result,
            "frequency_magnitudes": frequency_magnitudes,
            "dominant_frequencies": dominant_frequencies,
            "frequency_stats": frequency_stats,
        }

    def _calculate_beating_frequencies(
        self, frequency_spectrum: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Calculate beating frequencies from frequency spectrum.

        Physical Meaning:
            Calculates beating frequencies as differences between
            dominant frequencies, representing mode interactions.

        Args:
            frequency_spectrum (Dict[str, Any]): Frequency spectrum analysis results.

        Returns:
            List[Dict[str, Any]]: List of beating frequency analysis results.
        """
        dominant_frequencies = frequency_spectrum["dominant_frequencies"]
        beating_frequencies = []

        # Calculate beating frequencies between all pairs of dominant frequencies
        for i in range(len(dominant_frequencies)):
            for j in range(i + 1, len(dominant_frequencies)):
                freq_i = dominant_frequencies[i]
                freq_j = dominant_frequencies[j]

                # Calculate beating frequency
                beating_freq = abs(freq_i["frequency"] - freq_j["frequency"])

                # Calculate beating amplitude
                beating_amplitude = min(freq_i["amplitude"], freq_j["amplitude"])

                beating_frequencies.append(
                    {
                        "frequency": beating_freq,
                        "amplitude": beating_amplitude,
                        "source_frequencies": [
                            freq_i["frequency"],
                            freq_j["frequency"],
                        ],
                        "source_amplitudes": [freq_i["amplitude"], freq_j["amplitude"]],
                    }
                )

        return beating_frequencies

    def _calculate_interference_patterns(
        self, envelope: np.ndarray, beating_frequencies: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate interference patterns from beating frequencies.

        Physical Meaning:
            Calculates interference patterns that result from
            beating between different frequency modes.

        Args:
            envelope (np.ndarray): 7D envelope field data.
            beating_frequencies (List[Dict[str, Any]]): Beating frequency analysis results.

        Returns:
            Dict[str, Any]: Interference pattern analysis results.
        """
        # Calculate interference patterns
        interference_patterns = {}

        for beating_freq in beating_frequencies:
            freq = beating_freq["frequency"]
            amplitude = beating_freq["amplitude"]

            # Calculate interference pattern for this beating frequency
            pattern = self._calculate_single_interference_pattern(
                envelope, freq, amplitude
            )
            interference_patterns[f"pattern_{freq}"] = pattern

        # Calculate overall interference statistics
        interference_stats = self._calculate_interference_statistics(
            interference_patterns
        )

        return {"patterns": interference_patterns, "statistics": interference_stats}

    def _calculate_spectrum_statistics(
        self,
        frequency_spectrum: Dict[str, Any],
        beating_frequencies: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate spectrum statistics.

        Physical Meaning:
            Calculates statistical measures of the frequency spectrum
            and beating frequencies for analysis.

        Args:
            frequency_spectrum (Dict[str, Any]): Frequency spectrum analysis results.
            beating_frequencies (List[Dict[str, Any]]): Beating frequency analysis results.

        Returns:
            Dict[str, Any]: Spectrum statistics.
        """
        # Calculate frequency spectrum statistics
        frequency_magnitudes = frequency_spectrum["frequency_magnitudes"]
        freq_stats = {
            "max_frequency": float(np.max(frequency_magnitudes)),
            "mean_frequency": float(np.mean(frequency_magnitudes)),
            "std_frequency": float(np.std(frequency_magnitudes)),
            "total_power": float(np.sum(frequency_magnitudes**2)),
        }

        # Calculate beating frequency statistics
        if beating_frequencies:
            beating_freqs = [bf["frequency"] for bf in beating_frequencies]
            beating_amps = [bf["amplitude"] for bf in beating_frequencies]

            beating_stats = {
                "num_beating_frequencies": len(beating_frequencies),
                "max_beating_frequency": float(np.max(beating_freqs)),
                "mean_beating_frequency": float(np.mean(beating_freqs)),
                "max_beating_amplitude": float(np.max(beating_amps)),
                "mean_beating_amplitude": float(np.mean(beating_amps)),
            }
        else:
            beating_stats = {
                "num_beating_frequencies": 0,
                "max_beating_frequency": 0.0,
                "mean_beating_frequency": 0.0,
                "max_beating_amplitude": 0.0,
                "mean_beating_amplitude": 0.0,
            }

        return {"frequency_spectrum": freq_stats, "beating_frequencies": beating_stats}

    def _find_dominant_frequencies(
        self, frequency_magnitudes: np.ndarray
    ) -> List[Dict[str, Any]]:
        """
        Find dominant frequencies in the spectrum.

        Physical Meaning:
            Identifies the most significant frequencies in the
            spectrum based on their amplitudes.

        Args:
            frequency_magnitudes (np.ndarray): Frequency magnitude spectrum.

        Returns:
            List[Dict[str, Any]]: List of dominant frequency information.
        """
        # Find peaks in the frequency spectrum
        peaks = self._find_peaks(frequency_magnitudes)

        # Sort peaks by amplitude
        peaks.sort(key=lambda x: x["amplitude"], reverse=True)

        # Return top 10 peaks
        return peaks[:10]

    def _find_peaks(self, data: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find peaks in the data.

        Physical Meaning:
            Identifies local maxima in the data that represent
            significant frequency components.

        Args:
            data (np.ndarray): Input data array.

        Returns:
            List[Dict[str, Any]]: List of peak information.
        """
        peaks = []

        # Simple peak finding algorithm
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1]:
                peaks.append(
                    {"index": i, "frequency": float(i), "amplitude": float(data[i])}
                )

        return peaks

    def _calculate_frequency_statistics(
        self, frequency_magnitudes: np.ndarray
    ) -> Dict[str, float]:
        """
        Calculate frequency statistics.

        Physical Meaning:
            Calculates statistical measures of the frequency
            magnitudes for analysis.

        Args:
            frequency_magnitudes (np.ndarray): Frequency magnitude spectrum.

        Returns:
            Dict[str, float]: Frequency statistics.
        """
        return {
            "max_magnitude": float(np.max(frequency_magnitudes)),
            "mean_magnitude": float(np.mean(frequency_magnitudes)),
            "std_magnitude": float(np.std(frequency_magnitudes)),
            "total_power": float(np.sum(frequency_magnitudes**2)),
        }

    def _calculate_single_interference_pattern(
        self, envelope: np.ndarray, frequency: float, amplitude: float
    ) -> Dict[str, Any]:
        """
        Calculate interference pattern for a single beating frequency.

        Physical Meaning:
            Calculates the interference pattern that results from
            beating at a specific frequency.

        Args:
            envelope (np.ndarray): 7D envelope field data.
            frequency (float): Beating frequency.
            amplitude (float): Beating amplitude.

        Returns:
            Dict[str, Any]: Interference pattern information.
        """
        # Calculate interference pattern
        interference_pattern = amplitude * np.sin(
            2 * np.pi * frequency * np.arange(len(envelope.flatten()))
        )

        # Calculate pattern statistics
        pattern_stats = {
            "max_amplitude": float(np.max(interference_pattern)),
            "mean_amplitude": float(np.mean(interference_pattern)),
            "std_amplitude": float(np.std(interference_pattern)),
            "frequency": frequency,
            "amplitude": amplitude,
        }

        return {"pattern": interference_pattern.tolist(), "statistics": pattern_stats}

    def _calculate_interference_statistics(
        self, interference_patterns: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate interference pattern statistics.

        Physical Meaning:
            Calculates statistical measures of the interference
            patterns for analysis.

        Args:
            interference_patterns (Dict[str, Any]): Interference pattern analysis results.

        Returns:
            Dict[str, Any]: Interference pattern statistics.
        """
        if not interference_patterns:
            return {
                "num_patterns": 0,
                "max_amplitude": 0.0,
                "mean_amplitude": 0.0,
                "std_amplitude": 0.0,
            }

        # Calculate statistics across all patterns
        all_amplitudes = []
        for pattern_name, pattern_data in interference_patterns.items():
            stats = pattern_data["statistics"]
            all_amplitudes.append(stats["max_amplitude"])

        return {
            "num_patterns": len(interference_patterns),
            "max_amplitude": float(np.max(all_amplitudes)),
            "mean_amplitude": float(np.mean(all_amplitudes)),
            "std_amplitude": float(np.std(all_amplitudes)),
        }
