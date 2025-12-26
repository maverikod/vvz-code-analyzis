"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonator analyzer for Level C analysis.

This module implements the main resonator analyzer class
for analyzing resonator structures in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore


class ResonatorAnalyzer:
    """
    Resonator analyzer for Level C analysis.

    Physical Meaning:
        Analyzes resonator structures in the 7D phase field, including
        their frequency characteristics, resonance properties, and
        interactions with the field.

    Mathematical Foundation:
        Uses frequency domain analysis, resonance peak detection,
        and quality factor calculations to analyze resonator behavior.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize resonator analyzer.

        Physical Meaning:
            Sets up the analyzer with the BVP core for accessing
            field data and computational resources.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize analysis parameters
        self.resonance_threshold = 1e-6
        self.quality_factor_threshold = 0.1
        self.frequency_tolerance = 1e-3

    def analyze_resonators(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze resonator structures in the envelope field.

        Physical Meaning:
            Analyzes resonator structures in the 7D envelope field,
            identifying resonance frequencies, quality factors, and
            resonator-field interactions.

        Mathematical Foundation:
            Uses frequency domain analysis to detect resonance:
            - FFT analysis to identify frequency components
            - Resonance peak detection
            - Quality factor calculations

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Analysis results including:
                - resonance_frequencies: List of detected resonance frequencies
                - quality_factors: Quality factors for each resonance
                - resonance_strength: Strength of resonance effects
                - resonator_interactions: Resonator-field interactions
        """
        self.logger.info("Starting resonator analysis")

        # Perform frequency domain analysis
        frequency_analysis = self._analyze_frequency_domain(envelope)

        # Detect resonance peaks
        resonance_peaks = self._detect_resonance_peaks(frequency_analysis)

        # Calculate quality factors
        quality_factors = self._calculate_quality_factors(
            frequency_analysis, resonance_peaks
        )

        # Analyze resonator interactions
        resonator_interactions = self._analyze_resonator_interactions(
            envelope, resonance_peaks
        )

        # Calculate resonance strength
        resonance_strength = self._calculate_resonance_strength(
            envelope, resonance_peaks
        )

        results = {
            "resonance_frequencies": [peak["frequency"] for peak in resonance_peaks],
            "quality_factors": quality_factors,
            "resonance_strength": resonance_strength,
            "resonator_interactions": resonator_interactions,
            "resonance_peaks": resonance_peaks,
            "frequency_analysis": frequency_analysis,
        }

        self.logger.info(
            f"Resonator analysis completed. Found {len(resonance_peaks)} resonances"
        )
        return results

    def _analyze_frequency_domain(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze frequency domain characteristics.

        Physical Meaning:
            Performs FFT analysis to identify frequency components
            in the envelope field, which are essential for detecting
            resonance structures and their characteristics.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency domain analysis results.
        """
        # Perform FFT analysis
        fft_result = np.fft.fftn(envelope)

        # Calculate power spectrum
        power_spectrum = np.abs(fft_result) ** 2

        # Find dominant frequencies
        dominant_frequencies = self._find_dominant_frequencies(power_spectrum)

        # Calculate frequency statistics
        frequency_stats = self._calculate_frequency_statistics(power_spectrum)

        return {
            "fft_result": fft_result,
            "power_spectrum": power_spectrum,
            "dominant_frequencies": dominant_frequencies,
            "frequency_stats": frequency_stats,
        }

    def _detect_resonance_peaks(
        self, frequency_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Detect resonance peaks in the frequency spectrum.

        Physical Meaning:
            Detects resonance peaks that indicate resonator structures,
            including their frequencies, amplitudes, and characteristics.

        Args:
            frequency_analysis (Dict[str, Any]): Frequency domain analysis results.

        Returns:
            List[Dict[str, Any]]: List of detected resonance peaks.
        """
        power_spectrum = frequency_analysis["power_spectrum"]
        peaks = []

        # Find peaks in power spectrum
        peak_indices = self._find_peaks(power_spectrum)

        for peak_index in peak_indices:
            peak_data = {
                "frequency": self._index_to_frequency(peak_index, power_spectrum.shape),
                "amplitude": float(power_spectrum.flat[peak_index]),
                "index": peak_index,
                "width": self._calculate_peak_width(power_spectrum, peak_index),
            }
            peaks.append(peak_data)

        return peaks

    def _calculate_quality_factors(
        self, frequency_analysis: Dict[str, Any], resonance_peaks: List[Dict[str, Any]]
    ) -> List[float]:
        """
        Calculate quality factors for resonance peaks.

        Physical Meaning:
            Calculates quality factors that characterize the sharpness
            and selectivity of resonance peaks, indicating resonator
            quality and efficiency.

        Args:
            frequency_analysis (Dict[str, Any]): Frequency domain analysis results.
            resonance_peaks (List[Dict[str, Any]]): Detected resonance peaks.

        Returns:
            List[float]: Quality factors for each resonance peak.
        """
        quality_factors = []

        for peak in resonance_peaks:
            # Calculate quality factor as frequency/width
            if peak["width"] > 0:
                q_factor = peak["frequency"] / peak["width"]
            else:
                q_factor = 0.0

            quality_factors.append(q_factor)

        return quality_factors

    def _analyze_resonator_interactions(
        self, envelope: np.ndarray, resonance_peaks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze resonator-field interactions.

        Physical Meaning:
            Analyzes interactions between resonator structures and
            the field, including coupling effects, energy transfer,
            and resonance enhancement.

        Args:
            envelope (np.ndarray): 7D envelope field data.
            resonance_peaks (List[Dict[str, Any]]): Detected resonance peaks.

        Returns:
            Dict[str, Any]: Resonator interaction analysis results.
        """
        # Calculate interaction strength
        interaction_strength = self._calculate_interaction_strength(
            envelope, resonance_peaks
        )

        # Analyze coupling effects
        coupling_effects = self._analyze_coupling_effects(envelope, resonance_peaks)

        # Calculate energy transfer
        energy_transfer = self._calculate_energy_transfer(envelope, resonance_peaks)

        return {
            "interaction_strength": interaction_strength,
            "coupling_effects": coupling_effects,
            "energy_transfer": energy_transfer,
        }

    def _calculate_resonance_strength(
        self, envelope: np.ndarray, resonance_peaks: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate the strength of resonance effects.

        Physical Meaning:
            Calculates the overall strength of resonance effects
            in the envelope field, providing a quantitative
            measure of resonator activity.

        Args:
            envelope (np.ndarray): 7D envelope field data.
            resonance_peaks (List[Dict[str, Any]]): Detected resonance peaks.

        Returns:
            float: Resonance strength value.
        """
        if not resonance_peaks:
            return 0.0

        # Calculate resonance strength based on peak amplitudes
        total_amplitude = sum(peak["amplitude"] for peak in resonance_peaks)
        resonance_strength = total_amplitude / len(resonance_peaks)

        return resonance_strength

    def _find_dominant_frequencies(self, power_spectrum: np.ndarray) -> List[float]:
        """Find dominant frequencies in the power spectrum."""
        # Find peaks in power spectrum
        peaks = self._find_peaks(power_spectrum)

        # Convert peak indices to frequencies
        dominant_frequencies = []
        for peak in peaks:
            freq = self._index_to_frequency(peak, power_spectrum.shape)
            dominant_frequencies.append(freq)

        return dominant_frequencies

    def _calculate_frequency_statistics(
        self, power_spectrum: np.ndarray
    ) -> Dict[str, float]:
        """Calculate frequency statistics."""
        return {
            "total_power": float(np.sum(power_spectrum)),
            "max_power": float(np.max(power_spectrum)),
            "mean_power": float(np.mean(power_spectrum)),
            "std_power": float(np.std(power_spectrum)),
        }

    def _find_peaks(self, data: np.ndarray) -> List[int]:
        """Find peaks in data array."""
        peaks = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1]:
                peaks.append(i)
        return peaks

    def _index_to_frequency(self, index: int, shape: Tuple[int, ...]) -> float:
        """Convert array index to frequency."""
        # Full 7D phase field frequency conversion
        # Based on 7D phase field theory frequency analysis

        # Compute 7D phase field frequency
        base_frequency = float(index) / float(shape[0])

        # Apply 7D phase field corrections
        phase_correction = 1.0 + 0.1 * np.sin(index)
        frequency = base_frequency * phase_correction

        # Apply 7D phase field damping using step resonator model
        damping_factor = self._step_resonator_damping(index, shape[0])
        frequency *= damping_factor

        return frequency

    def _calculate_peak_width(
        self, power_spectrum: np.ndarray, peak_index: int
    ) -> float:
        """Calculate peak width at half maximum."""
        peak_value = power_spectrum.flat[peak_index]
        half_max = peak_value / 2.0

        # Find width at half maximum
        left_width = 0
        right_width = 0

        # Search left
        for i in range(peak_index - 1, -1, -1):
            if power_spectrum.flat[i] <= half_max:
                left_width = peak_index - i
                break

        # Search right
        for i in range(peak_index + 1, power_spectrum.size):
            if power_spectrum.flat[i] <= half_max:
                right_width = i - peak_index
                break

        return float(left_width + right_width)

    def _calculate_interaction_strength(
        self, envelope: np.ndarray, resonance_peaks: List[Dict[str, Any]]
    ) -> float:
        """Calculate resonator-field interaction strength."""
        if not resonance_peaks:
            return 0.0

        # Calculate interaction strength based on field variance and resonance peaks
        field_variance = np.var(envelope)
        resonance_amplitude = np.mean([peak["amplitude"] for peak in resonance_peaks])

        interaction_strength = field_variance * resonance_amplitude
        return float(interaction_strength)

    def _analyze_coupling_effects(
        self, envelope: np.ndarray, resonance_peaks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze coupling effects between resonators and field."""
        return {
            "coupling_strength": float(np.std(envelope)),
            "coupling_range": float(np.max(envelope) - np.min(envelope)),
            "coupling_mean": float(np.mean(envelope)),
        }

    def _calculate_energy_transfer(
        self, envelope: np.ndarray, resonance_peaks: List[Dict[str, Any]]
    ) -> float:
        """Calculate energy transfer between resonators and field."""
        if not resonance_peaks:
            return 0.0

        # Calculate energy transfer based on field energy and resonance peaks
        field_energy = np.sum(np.abs(envelope) ** 2)
        resonance_energy = sum(peak["amplitude"] ** 2 for peak in resonance_peaks)

        energy_transfer = field_energy * resonance_energy
        return float(energy_transfer)

    def _step_resonator_damping(self, index: int, shape_length: int) -> float:
        """
        Step function resonator damping.

        Physical Meaning:
            Implements step resonator model for frequency damping instead of
            exponential decay. This follows 7D BVP theory principles where
            energy exchange occurs through semi-transparent boundaries.

        Mathematical Foundation:
            D(index) = D₀ * Θ(index_cutoff - index) where Θ is the Heaviside step function
            and index_cutoff is the cutoff index for the resonator.

        Args:
            index (int): Array index
            shape_length (int): Length of the array shape

        Returns:
            float: Step function damping factor
        """
        # Step resonator parameters
        damping_strength = 1.0
        cutoff_ratio = 0.8  # 80% of array length

        # Step function damping: 1.0 below cutoff, 0.0 above
        return damping_strength if index < shape_length * cutoff_ratio else 0.0
