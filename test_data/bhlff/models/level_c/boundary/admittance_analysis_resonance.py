"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Admittance analysis resonance module.

This module implements resonance analysis functionality for admittance analysis
in Level C test C1 of 7D phase field theory.

Physical Meaning:
    Analyzes resonance effects in admittance spectrum,
    including resonance detection and quality factor analysis.

Example:
    >>> resonance_analyzer = AdmittanceResonanceAnalyzer(bvp_core)
    >>> resonances = resonance_analyzer.detect_resonances(spectrum, threshold)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, AdmittanceSpectrum


class AdmittanceResonanceAnalyzer:
    """
    Admittance resonance analyzer for boundary effects.

    Physical Meaning:
        Analyzes resonance effects in admittance spectrum,
        including resonance detection and quality factor analysis.

    Mathematical Foundation:
        Implements resonance analysis:
        - Resonance detection: peaks in |Y(ω)| spectrum
        - Quality factor analysis: Q = ω / (2 * Δω)
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize admittance resonance analyzer.

        Physical Meaning:
            Sets up the resonance analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def detect_resonances(
        self, spectrum: AdmittanceSpectrum, threshold: float = 8.0
    ) -> List[Dict[str, Any]]:
        """
        Detect resonances in admittance spectrum.

        Physical Meaning:
            Detects resonances in admittance spectrum
            based on peak analysis and quality factor.

        Mathematical Foundation:
            Resonance detection: peaks in |Y(ω)| spectrum
            Quality factor analysis: Q = ω / (2 * Δω)

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            threshold (float): Detection threshold.

        Returns:
            List[Dict[str, Any]]: Detected resonances.
        """
        self.logger.info("Detecting resonances in admittance spectrum")

        # Find peaks in magnitude spectrum
        peaks = self._find_peaks(spectrum.magnitude, threshold)

        # Analyze each resonance peak
        resonances = []
        for peak_index in peaks:
            resonance = self._analyze_resonance_peak(spectrum, peak_index)
            resonances.append(resonance)

        self.logger.info(f"Detected {len(resonances)} resonances")
        return resonances

    def _find_peaks(self, signal: np.ndarray, height: float) -> List[int]:
        """
        Find peaks in signal.

        Physical Meaning:
            Finds peaks in signal using peak detection
            algorithm for resonance analysis.

        Args:
            signal (np.ndarray): Signal to analyze.
            height (float): Minimum peak height.

        Returns:
            List[int]: Peak indices.
        """
        # Simplified peak finding
        # In practice, this would involve proper peak detection
        peaks = []

        # Find local maxima
        for i in range(1, len(signal) - 1):
            if (
                signal[i] > signal[i - 1]
                and signal[i] > signal[i + 1]
                and signal[i] > height
            ):
                peaks.append(i)

        return peaks

    def _analyze_resonance_peak(
        self, spectrum: AdmittanceSpectrum, peak_index: int
    ) -> Dict[str, Any]:
        """
        Analyze resonance peak.

        Physical Meaning:
            Analyzes individual resonance peak to extract
            resonance parameters and quality factor.

        Mathematical Foundation:
            Quality factor analysis: Q = ω / (2 * Δω)

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.

        Returns:
            Dict[str, Any]: Resonance analysis results.
        """
        # Extract peak parameters
        frequency = spectrum.frequencies[peak_index]
        magnitude = spectrum.magnitude[peak_index]
        phase = spectrum.phase[peak_index]

        # Compute quality factor
        quality_factor = self._compute_quality_factor(spectrum, peak_index)

        # Calculate resonance width
        resonance_width = self._calculate_resonance_width(spectrum, peak_index)

        # Calculate resonance strength
        resonance_strength = self._calculate_resonance_strength(spectrum, peak_index)

        return {
            "frequency": frequency,
            "magnitude": magnitude,
            "phase": phase,
            "quality_factor": quality_factor,
            "resonance_width": resonance_width,
            "resonance_strength": resonance_strength,
            "peak_index": peak_index,
        }

    def _compute_quality_factor(
        self, spectrum: AdmittanceSpectrum, peak_index: int
    ) -> float:
        """
        Compute quality factor.

        Physical Meaning:
            Computes quality factor for resonance peak
            based on resonance width analysis.

        Mathematical Foundation:
            Quality factor: Q = ω / (2 * Δω)
            where Δω is the full width at half maximum

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.

        Returns:
            float: Quality factor.
        """
        # Find full width at half maximum
        peak_magnitude = spectrum.magnitude[peak_index]
        half_maximum = peak_magnitude / 2.0

        # Find left and right boundaries
        left_boundary = self._find_left_boundary(spectrum, peak_index, half_maximum)
        right_boundary = self._find_right_boundary(spectrum, peak_index, half_maximum)

        # Calculate resonance width
        resonance_width = (
            spectrum.frequencies[right_boundary] - spectrum.frequencies[left_boundary]
        )

        # Calculate quality factor
        if resonance_width > 0:
            quality_factor = spectrum.frequencies[peak_index] / resonance_width
        else:
            quality_factor = float("inf")

        return quality_factor

    def _find_left_boundary(
        self, spectrum: AdmittanceSpectrum, peak_index: int, half_maximum: float
    ) -> int:
        """
        Find left boundary of resonance.

        Physical Meaning:
            Finds left boundary of resonance peak
            at half maximum level.

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.
            half_maximum (float): Half maximum level.

        Returns:
            int: Left boundary index.
        """
        # Search left from peak
        for i in range(peak_index - 1, -1, -1):
            if spectrum.magnitude[i] <= half_maximum:
                return i

        return 0

    def _find_right_boundary(
        self, spectrum: AdmittanceSpectrum, peak_index: int, half_maximum: float
    ) -> int:
        """
        Find right boundary of resonance.

        Physical Meaning:
            Finds right boundary of resonance peak
            at half maximum level.

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.
            half_maximum (float): Half maximum level.

        Returns:
            int: Right boundary index.
        """
        # Search right from peak
        for i in range(peak_index + 1, len(spectrum.magnitude)):
            if spectrum.magnitude[i] <= half_maximum:
                return i

        return len(spectrum.magnitude) - 1

    def _calculate_resonance_width(
        self, spectrum: AdmittanceSpectrum, peak_index: int
    ) -> float:
        """
        Calculate resonance width.

        Physical Meaning:
            Calculates resonance width for quality factor
            analysis.

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.

        Returns:
            float: Resonance width.
        """
        # Find full width at half maximum
        peak_magnitude = spectrum.magnitude[peak_index]
        half_maximum = peak_magnitude / 2.0

        # Find boundaries
        left_boundary = self._find_left_boundary(spectrum, peak_index, half_maximum)
        right_boundary = self._find_right_boundary(spectrum, peak_index, half_maximum)

        # Calculate width
        resonance_width = (
            spectrum.frequencies[right_boundary] - spectrum.frequencies[left_boundary]
        )

        return resonance_width

    def _calculate_resonance_strength(
        self, spectrum: AdmittanceSpectrum, peak_index: int
    ) -> float:
        """
        Calculate resonance strength.

        Physical Meaning:
            Calculates resonance strength based on
            peak magnitude and background level.

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            peak_index (int): Peak index.

        Returns:
            float: Resonance strength.
        """
        # Calculate background level
        background_level = np.mean(spectrum.magnitude)

        # Calculate resonance strength
        resonance_strength = spectrum.magnitude[peak_index] - background_level

        return resonance_strength
