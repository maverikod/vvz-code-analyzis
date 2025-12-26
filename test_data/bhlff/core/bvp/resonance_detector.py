"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core resonance detection algorithms for BVP impedance analysis.

This module implements the core functionality for detecting resonance peaks
in impedance/admittance spectra, including quality factor estimation
and peak characterization.

Physical Meaning:
    Provides algorithms for identifying resonance frequencies and quality
    factors from impedance spectra, representing the system's resonant
    behavior and energy storage characteristics.

Mathematical Foundation:
    Implements advanced signal processing techniques including magnitude,
    phase, and derivative analysis for robust peak detection.

Example:
    >>> detector = ResonanceDetector()
    >>> peaks = detector.find_resonance_peaks(frequencies, admittance)
"""

import numpy as np
from typing import Dict, List, Optional

from .bvp_constants import BVPConstants
from .resonance_peak_detector import ResonancePeakDetector
from .resonance_quality_analyzer import ResonanceQualityAnalysis


class ResonanceDetector:
    """
    Advanced resonance detection algorithms for impedance analysis.

    Physical Meaning:
        Implements advanced algorithms for identifying resonance frequencies
        and quality factors from impedance spectra.

    Mathematical Foundation:
        Uses multiple criteria for peak detection:
        1. Local maxima in magnitude with sufficient prominence
        2. Phase behavior analysis (rapid phase changes)
        3. Second derivative analysis for peak sharpness
        4. Quality factor estimation using Lorentzian fitting
    """

    def __init__(self, constants: Optional[BVPConstants] = None) -> None:
        """
        Initialize resonance detector.

        Args:
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.constants = constants or BVPConstants()
        self.quality_factor_threshold = self.constants.get_impedance_parameter(
            "quality_factor_threshold"
        )

        # Initialize helper components
        self.peak_detector = ResonancePeakDetector(self.constants)
        self.quality_analyzer = ResonanceQualityAnalysis(self.constants)

    def find_resonance_peaks(
        self, frequencies: np.ndarray, admittance: np.ndarray
    ) -> Dict[str, List[float]]:
        """
        Find resonance peaks in admittance.

        Physical Meaning:
            Identifies resonance frequencies and quality factors
            from the admittance spectrum.

        Args:
            frequencies (np.ndarray): Frequency array.
            admittance (np.ndarray): Admittance Y(ω).

        Returns:
            Dict[str, List[float]]: Resonance peaks including frequencies and
            quality factors.
        """
        # Find peaks in admittance magnitude using advanced algorithms
        admittance_magnitude = np.abs(admittance)
        admittance_phase = np.angle(admittance)

        # Advanced peak detection using multiple criteria
        peaks, quality_factors = self.peak_detector.detect_peaks(
            frequencies, admittance_magnitude, admittance_phase
        )

        return {"frequencies": peaks, "quality_factors": quality_factors}

    def set_quality_factor_threshold(self, threshold: float) -> None:
        """
        Set quality factor threshold for peak filtering.

        Args:
            threshold (float): Quality factor threshold.
        """
        self.quality_factor_threshold = threshold

    def get_quality_factor_threshold(self) -> float:
        """
        Get current quality factor threshold.

        Returns:
            float: Current quality factor threshold.
        """
        return self.quality_factor_threshold

    def __repr__(self) -> str:
        """String representation of resonance detector."""
        return f"ResonanceDetector(threshold={self.quality_factor_threshold})"
