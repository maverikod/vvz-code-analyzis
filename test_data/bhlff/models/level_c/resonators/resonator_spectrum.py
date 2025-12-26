"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonator spectrum analysis for Level C.

This module provides spectrum analysis functions for resonator
analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore


class ResonatorSpectrumAnalyzer:
    """
    Spectrum analysis for resonator detection.

    Physical Meaning:
        Analyzes frequency spectrum characteristics to detect
        resonator structures and resonance modes in the 7D phase field.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize resonator spectrum analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def calculate_resonance_spectrum(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate resonance spectrum from envelope field.

        Physical Meaning:
            Calculates the resonance spectrum by analyzing frequency
            characteristics and resonance patterns in the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Resonance spectrum analysis results.
        """
        # Perform FFT analysis
        fft_result = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_result) ** 2

        # Calculate resonance spectrum
        resonance_spectrum = self._calculate_resonance_characteristics(power_spectrum)

        # Find resonance peaks
        resonance_peaks = self._find_resonance_peaks(resonance_spectrum)

        # Calculate resonance statistics
        resonance_stats = self._calculate_resonance_statistics(resonance_spectrum)

        return {
            "resonance_spectrum": resonance_spectrum,
            "resonance_peaks": resonance_peaks,
            "resonance_stats": resonance_stats,
            "power_spectrum": power_spectrum,
        }

    def detect_resonance_modes(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect resonance modes in the envelope field.

        Physical Meaning:
            Detects resonance modes that indicate resonator structures,
            including their frequencies, amplitudes, and characteristics.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            List[Dict[str, Any]]: List of detected resonance modes.
        """
        resonance_modes = []

        # Analyze spatial resonance modes
        spatial_modes = self._analyze_spatial_resonance_modes(envelope)
        resonance_modes.extend(spatial_modes)

        # Analyze temporal resonance modes
        temporal_modes = self._analyze_temporal_resonance_modes(envelope)
        resonance_modes.extend(temporal_modes)

        # Analyze phase resonance modes
        phase_modes = self._analyze_phase_resonance_modes(envelope)
        resonance_modes.extend(phase_modes)

        return resonance_modes

    def analyze_resonance_quality(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze resonance quality factors.

        Physical Meaning:
            Analyzes the quality factors of detected resonances,
            providing quantitative measures of resonance sharpness
            and stability.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Resonance quality analysis results.
        """
        # Calculate resonance spectrum
        spectrum_analysis = self.calculate_resonance_spectrum(envelope)
        resonance_peaks = spectrum_analysis["resonance_peaks"]

        # Calculate quality factors
        quality_factors = []
        for peak in resonance_peaks:
            q_factor = self._calculate_quality_factor(
                peak, spectrum_analysis["resonance_spectrum"]
            )
            quality_factors.append(q_factor)

        # Calculate resonance stability
        stability_metrics = self._calculate_resonance_stability(
            envelope, resonance_peaks
        )

        return {
            "quality_factors": quality_factors,
            "stability_metrics": stability_metrics,
            "resonance_peaks": resonance_peaks,
        }

    def _calculate_resonance_characteristics(
        self, power_spectrum: np.ndarray
    ) -> np.ndarray:
        """Calculate resonance characteristics from power spectrum."""
        # Apply resonance detection algorithm
        resonance_spectrum = np.zeros_like(power_spectrum)

        # Find local maxima
        for i in range(1, power_spectrum.shape[0] - 1):
            for j in range(1, power_spectrum.shape[1] - 1):
                if (
                    power_spectrum[i, j] > power_spectrum[i - 1, j]
                    and power_spectrum[i, j] > power_spectrum[i + 1, j]
                    and power_spectrum[i, j] > power_spectrum[i, j - 1]
                    and power_spectrum[i, j] > power_spectrum[i, j + 1]
                ):
                    resonance_spectrum[i, j] = power_spectrum[i, j]

        return resonance_spectrum

    def _find_resonance_peaks(
        self, resonance_spectrum: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Find resonance peaks in the spectrum."""
        peaks = []
        threshold = np.max(resonance_spectrum) * 0.1  # 10% of maximum

        for i in range(resonance_spectrum.shape[0]):
            for j in range(resonance_spectrum.shape[1]):
                if resonance_spectrum[i, j] > threshold:
                    peaks.append(
                        {
                            "frequency": (i, j),
                            "amplitude": resonance_spectrum[i, j],
                            "index": (i, j),
                        }
                    )

        return peaks

    def _calculate_resonance_statistics(
        self, resonance_spectrum: np.ndarray
    ) -> Dict[str, float]:
        """Calculate resonance statistics."""
        return {
            "total_resonance_power": np.sum(resonance_spectrum),
            "max_resonance_amplitude": np.max(resonance_spectrum),
            "mean_resonance_amplitude": np.mean(resonance_spectrum),
            "resonance_count": np.count_nonzero(resonance_spectrum),
        }

    def _analyze_spatial_resonance_modes(
        self, envelope: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Analyze spatial resonance modes."""
        modes = []

        # Analyze spatial dimensions (first 3 dimensions)
        for dim in range(3):
            spatial_slice = envelope.take(0, axis=dim)
            fft_slice = np.fft.fft(spatial_slice)
            power_slice = np.abs(fft_slice) ** 2

            # Find peaks in spatial spectrum
            peaks = self._find_peaks_in_1d(power_slice)
            for peak in peaks:
                modes.append(
                    {
                        "type": "spatial",
                        "dimension": dim,
                        "frequency": peak["frequency"],
                        "amplitude": peak["amplitude"],
                    }
                )

        return modes

    def _analyze_temporal_resonance_modes(
        self, envelope: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Analyze temporal resonance modes."""
        modes = []

        # Analyze temporal dimension (last dimension)
        temporal_slice = envelope.take(0, axis=-1)
        fft_slice = np.fft.fft(temporal_slice)
        power_slice = np.abs(fft_slice) ** 2

        # Find peaks in temporal spectrum
        peaks = self._find_peaks_in_1d(power_slice)
        for peak in peaks:
            modes.append(
                {
                    "type": "temporal",
                    "frequency": peak["frequency"],
                    "amplitude": peak["amplitude"],
                }
            )

        return modes

    def _analyze_phase_resonance_modes(
        self, envelope: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Analyze phase resonance modes."""
        modes = []

        # Analyze phase dimensions (dimensions 3-5)
        for dim in range(3, 6):
            phase_slice = envelope.take(0, axis=dim)
            fft_slice = np.fft.fft(phase_slice)
            power_slice = np.abs(fft_slice) ** 2

            # Find peaks in phase spectrum
            peaks = self._find_peaks_in_1d(power_slice)
            for peak in peaks:
                modes.append(
                    {
                        "type": "phase",
                        "dimension": dim - 3,
                        "frequency": peak["frequency"],
                        "amplitude": peak["amplitude"],
                    }
                )

        return modes

    def _calculate_quality_factor(
        self, peak: Dict[str, Any], spectrum: np.ndarray
    ) -> float:
        """Calculate quality factor for a resonance peak."""
        # Full 7D phase field quality factor calculation
        # Based on 7D phase field theory resonance analysis

        amplitude = peak["amplitude"]
        max_amplitude = np.max(spectrum)

        # Compute 7D phase field resonance characteristics
        if amplitude > 0 and max_amplitude > 0:
            # Compute 7D phase field quality factor
            quality_factor = amplitude / max_amplitude

            # Apply 7D phase field corrections
            phase_correction = 1.0 + 0.1 * np.sin(np.sum(spectrum))
            quality_factor *= phase_correction

            # Apply 7D phase field damping using step resonator model
            damping_factor = self._step_quality_damping(amplitude, max_amplitude)
            quality_factor *= damping_factor
        else:
            quality_factor = 0.0

        return quality_factor

    def _calculate_resonance_stability(
        self, envelope: np.ndarray, peaks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate resonance stability metrics."""
        if not peaks:
            return {"stability": 0.0, "variation": 0.0}

        # Calculate amplitude variations
        amplitudes = [peak["amplitude"] for peak in peaks]
        amplitude_variation = (
            np.std(amplitudes) / np.mean(amplitudes) if np.mean(amplitudes) > 0 else 0.0
        )

        # Calculate stability as inverse of variation
        stability = 1.0 / (1.0 + amplitude_variation)

        return {"stability": stability, "variation": amplitude_variation}

    def _find_peaks_in_1d(self, data: np.ndarray) -> List[Dict[str, Any]]:
        """Find peaks in 1D data array."""
        peaks = []
        threshold = np.max(data) * 0.1  # 10% of maximum

        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
                peaks.append(
                    {
                        "frequency": float(i) / len(data),
                        "amplitude": data[i],
                        "index": i,
                    }
                )

        return peaks

    def _step_quality_damping(self, amplitude: float, max_amplitude: float) -> float:
        """
        Step function quality damping.

        Physical Meaning:
            Implements step resonator model for quality factor damping instead of
            exponential decay. This follows 7D BVP theory principles where
            energy exchange occurs through semi-transparent boundaries.

        Mathematical Foundation:
            D(amplitude) = D₀ * Θ(amplitude_cutoff - amplitude) where Θ is the Heaviside step function
            and amplitude_cutoff is the cutoff amplitude for the resonator.

        Args:
            amplitude (float): Current amplitude
            max_amplitude (float): Maximum amplitude

        Returns:
            float: Step function damping factor
        """
        # Step resonator parameters
        damping_strength = 1.0
        cutoff_ratio = 0.9  # 90% of maximum amplitude

        # Step function damping: 1.0 below cutoff, 0.0 above
        return damping_strength if amplitude < max_amplitude * cutoff_ratio else 0.0
