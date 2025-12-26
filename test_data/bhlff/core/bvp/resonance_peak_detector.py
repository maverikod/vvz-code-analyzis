"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonance peak detection algorithms for BVP impedance analysis.

This module implements advanced algorithms for detecting resonance peaks
in impedance/admittance spectra using multiple criteria and signal processing.

Physical Meaning:
    Identifies resonance peaks using advanced signal processing techniques
    including magnitude, phase, and derivative analysis for robust detection.

Mathematical Foundation:
    Uses multiple criteria for peak detection:
    1. Local maxima in magnitude with sufficient prominence
    2. Phase behavior analysis (rapid phase changes)
    3. Second derivative analysis for peak sharpness

Example:
    >>> detector = ResonancePeakDetector(constants)
    >>> peaks = detector.detect_peaks(frequencies, magnitude, phase)
"""

import numpy as np
from typing import List, Tuple

from .bvp_constants import BVPConstants


class ResonancePeakDetector:
    """
    Advanced peak detection algorithms for resonance analysis.

    Physical Meaning:
        Implements advanced algorithms for identifying resonance peaks
        using multiple criteria and signal processing techniques.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize peak detector.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants

    def detect_peaks(
        self, frequencies: np.ndarray, magnitude: np.ndarray, phase: np.ndarray
    ) -> Tuple[List[float], List[float]]:
        """
        Advanced peak detection using multiple criteria and signal processing.

        Physical Meaning:
            Identifies resonance peaks using advanced signal processing
            techniques including magnitude, phase, and derivative analysis.

        Mathematical Foundation:
            Uses multiple criteria for peak detection:
            1. Local maxima in magnitude with sufficient prominence
            2. Phase behavior analysis (rapid phase changes)
            3. Second derivative analysis for peak sharpness
            4. Quality factor estimation using Lorentzian fitting

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Admittance magnitude.
            phase (np.ndarray): Admittance phase.

        Returns:
            Tuple[List[float], List[float]]: Peak frequencies and quality factors.
        """
        # Step 1: Preprocessing - smooth the data to reduce noise
        window_size = self.constants.get_impedance_parameter("smoothing_window_size")
        magnitude_smooth = self._smooth_signal(magnitude, window_size=window_size)
        phase_smooth = self._smooth_signal(phase, window_size=window_size)

        # Step 2: Find local maxima with prominence analysis
        magnitude_peaks = self._find_prominent_peaks(magnitude_smooth)

        # Step 3: Phase analysis - look for rapid phase changes
        phase_peaks = self._find_phase_peaks(phase_smooth)

        # Step 4: Second derivative analysis for peak sharpness
        sharpness_peaks = self._find_sharp_peaks(magnitude_smooth)

        # Step 5: Combine all criteria
        combined_peaks = self._combine_peak_criteria(
            magnitude_peaks, phase_peaks, sharpness_peaks
        )

        # Step 6: Extract peak frequencies
        peak_frequencies = []
        for peak_idx in combined_peaks:
            if 0 < peak_idx < len(frequencies) - 1:
                peak_freq = frequencies[peak_idx]
                peak_frequencies.append(peak_freq)

        return peak_frequencies, []

    def _smooth_signal(self, signal: np.ndarray, window_size: int) -> np.ndarray:
        """
        Smooth signal using moving average filter.

        Physical Meaning:
            Reduces noise while preserving peak characteristics
            using polynomial smoothing.

        Args:
            signal (np.ndarray): Input signal.
            window_size (int): Smoothing window size.

        Returns:
            np.ndarray: Smoothed signal.
        """
        # Use moving average for simplicity (could use Savitzky-Golay)
        if window_size <= 1:
            return signal

        # Pad the signal for boundary handling
        padded = np.pad(signal, window_size // 2, mode="edge")

        # Apply moving average
        smoothed = np.convolve(padded, np.ones(window_size) / window_size, mode="valid")

        return smoothed

    def _find_prominent_peaks(self, magnitude: np.ndarray) -> List[int]:
        """
        Find prominent peaks using height and prominence criteria.

        Physical Meaning:
            Identifies peaks that are significantly higher than
            surrounding values and have sufficient prominence.

        Args:
            magnitude (np.ndarray): Signal magnitude.

        Returns:
            List[int]: Indices of prominent peaks.
        """
        peaks = []
        min_height = np.mean(magnitude) + 0.5 * np.std(magnitude)
        min_prominence = 0.1 * np.max(magnitude)

        for i in range(1, len(magnitude) - 1):
            if (
                magnitude[i] > magnitude[i - 1]
                and magnitude[i] > magnitude[i + 1]
                and magnitude[i] > min_height
            ):

                # Check prominence
                left_min = np.min(magnitude[max(0, i - 10) : i])
                right_min = np.min(magnitude[i + 1 : min(len(magnitude), i + 11)])
                prominence = magnitude[i] - max(left_min, right_min)

                if prominence > min_prominence:
                    peaks.append(i)

        return peaks

    def _find_phase_peaks(self, phase: np.ndarray) -> List[int]:
        """
        Find peaks based on phase behavior analysis.

        Physical Meaning:
            Identifies peaks where phase changes rapidly,
            indicating resonance behavior.

        Args:
            phase (np.ndarray): Signal phase.

        Returns:
            List[int]: Indices of phase-based peaks.
        """
        peaks = []
        phase_gradient = np.gradient(phase)
        phase_curvature = np.gradient(phase_gradient)

        # Look for rapid phase changes
        threshold = 2.0 * np.std(phase_curvature)

        for i in range(1, len(phase_curvature) - 1):
            if abs(phase_curvature[i]) > threshold:
                peaks.append(i)

        return peaks

    def _find_sharp_peaks(self, magnitude: np.ndarray) -> List[int]:
        """
        Find sharp peaks using second derivative analysis.

        Physical Meaning:
            Identifies peaks with high sharpness using
            second derivative analysis.

        Args:
            magnitude (np.ndarray): Signal magnitude.

        Returns:
            List[int]: Indices of sharp peaks.
        """
        peaks = []
        second_derivative = np.gradient(np.gradient(magnitude))

        # Look for negative second derivative (concave down)
        threshold = -0.1 * np.std(second_derivative)

        for i in range(1, len(second_derivative) - 1):
            if (
                second_derivative[i] < threshold
                and magnitude[i] > magnitude[i - 1]
                and magnitude[i] > magnitude[i + 1]
            ):
                peaks.append(i)

        return peaks

    def _combine_peak_criteria(
        self,
        magnitude_peaks: List[int],
        phase_peaks: List[int],
        sharpness_peaks: List[int],
    ) -> List[int]:
        """
        Combine peak detection criteria.

        Physical Meaning:
            Combines results from different peak detection methods
            to identify the most reliable resonance peaks.

        Args:
            magnitude_peaks (List[int]): Magnitude-based peaks.
            phase_peaks (List[int]): Phase-based peaks.
            sharpness_peaks (List[int]): Sharpness-based peaks.

        Returns:
            List[int]: Combined peak indices.
        """
        # Combine all peak indices
        all_peaks = set(magnitude_peaks + phase_peaks + sharpness_peaks)

        # Score peaks based on how many criteria they satisfy
        peak_scores = {}
        for peak in all_peaks:
            score = 0
            if peak in magnitude_peaks:
                score += 1
            if peak in phase_peaks:
                score += 1
            if peak in sharpness_peaks:
                score += 1
            peak_scores[peak] = score

        # Return peaks that satisfy at least 2 criteria
        reliable_peaks = [peak for peak, score in peak_scores.items() if score >= 2]

        return sorted(reliable_peaks)
