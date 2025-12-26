"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced resonance quality factor analysis for BVP impedance analysis.

This module implements the main resonance quality analysis functionality,
providing comprehensive analysis of resonance characteristics and quality factors.
"""

import numpy as np
from typing import List, Dict, Tuple

from .resonance_optimization import ResonanceOptimization
from .resonance_statistics import ResonanceStatistics
from ..bvp_constants import BVPConstants


class ResonanceQualityAnalysis:
    """
    Advanced resonance quality factor analysis.

    Physical Meaning:
        Provides advanced analysis of resonance quality factors for BVP impedance
        analysis, including comprehensive characterization of resonance properties
        and quality factor calculations.

    Mathematical Foundation:
        Analyzes resonance characteristics using advanced fitting techniques,
        statistical analysis, and quality factor optimization to provide
        accurate characterization of BVP resonance properties.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize advanced quality analyzer.

        Physical Meaning:
            Sets up the analyzer with BVP constants and initializes
            optimization and statistics modules for comprehensive analysis.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants
        self.optimization = ResonanceOptimization(constants)
        self.statistics = ResonanceStatistics(constants)

    def analyze_resonance_characteristics(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_indices: List[int]
    ) -> Dict[str, any]:
        """
        Analyze comprehensive resonance characteristics.

        Physical Meaning:
            Performs comprehensive analysis of resonance characteristics,
            including quality factors, resonance shapes, and
            frequency domain properties for BVP impedance analysis.

        Mathematical Foundation:
            Combines optimization techniques, statistical analysis, and
            resonance characterization to provide complete analysis
            of resonance properties.

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_indices (List[int]): List of peak indices.

        Returns:
            Dict[str, any]: Comprehensive resonance characteristics.
        """
        characteristics = {
            "quality_factors": [],
            "resonance_shapes": [],
            "frequency_properties": [],
            "amplitude_properties": [],
            "resonance_types": [],
        }

        for peak_idx in peak_indices:
            # Extract peak region
            peak_region = self._extract_peak_region(frequencies, magnitude, peak_idx)

            # Analyze resonance shape
            resonance_shape = self._analyze_resonance_shape(peak_region)
            characteristics["resonance_shapes"].append(resonance_shape)

            # Analyze frequency properties
            frequency_properties = self._analyze_frequency_properties(peak_region)
            characteristics["frequency_properties"].append(frequency_properties)

            # Analyze amplitude properties
            amplitude_properties = self._analyze_amplitude_properties(peak_region)
            characteristics["amplitude_properties"].append(amplitude_properties)

            # Classify resonance type
            resonance_type = self._classify_resonance_type(peak_region)
            characteristics["resonance_types"].append(resonance_type)

            # Calculate quality factor
            quality_factor = self._calculate_quality_factor_from_characteristics(
                resonance_shape, frequency_properties
            )
            characteristics["quality_factors"].append(quality_factor)

        return characteristics

    def compare_resonance_quality(
        self, quality_factors_1: List[float], quality_factors_2: List[float]
    ) -> Dict[str, float]:
        """
        Compare quality factors between two sets of resonances.

        Physical Meaning:
            Compares quality factors between two sets of resonances
            to analyze differences in resonance characteristics and
            identify systematic variations in BVP impedance properties.

        Mathematical Foundation:
            Uses statistical methods to compare quality factor distributions,
            including mean differences, standard deviations, correlations,
            and significance testing.

        Args:
            quality_factors_1 (List[float]): First set of quality factors.
            quality_factors_2 (List[float]): Second set of quality factors.

        Returns:
            Dict[str, float]: Comparison results.
        """
        return self.statistics.compare_quality_factors(
            quality_factors_1, quality_factors_2
        )

    def _extract_peak_region(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_idx: int
    ) -> Dict[str, np.ndarray]:
        """
        Extract region around a resonance peak.

        Physical Meaning:
            Extracts a localized region around a resonance peak for
            detailed analysis, ensuring sufficient data for accurate
            characterization while avoiding interference from nearby peaks.

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_idx (int): Index of the resonance peak.

        Returns:
            Dict[str, np.ndarray]: Peak region data.
        """
        # Define region width (adjustable parameter)
        region_width = 20  # Number of points around peak

        # Calculate region bounds
        start_idx = max(0, peak_idx - region_width // 2)
        end_idx = min(len(frequencies), peak_idx + region_width // 2 + 1)

        # Extract region
        region_frequencies = frequencies[start_idx:end_idx]
        region_magnitude = magnitude[start_idx:end_idx]

        return {
            "frequencies": region_frequencies,
            "magnitude": region_magnitude,
            "peak_idx": peak_idx - start_idx,
        }

    def _analyze_resonance_shape(
        self, peak_region: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Analyze resonance shape characteristics.

        Physical Meaning:
            Analyzes the shape characteristics of a resonance peak,
            including amplitude, width, and symmetry, which are
            crucial for understanding BVP impedance properties.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            Dict[str, float]: Resonance shape characteristics.
        """
        magnitude = peak_region["magnitude"]
        peak_idx = peak_region["peak_idx"]

        # Calculate shape metrics
        peak_amplitude = magnitude[peak_idx]
        peak_width = self._calculate_peak_width(magnitude, peak_idx)
        peak_symmetry = self._calculate_peak_symmetry(magnitude, peak_idx)

        return {
            "amplitude": peak_amplitude,
            "width": peak_width,
            "symmetry": peak_symmetry,
        }

    def _analyze_frequency_properties(
        self, peak_region: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Analyze frequency properties.

        Physical Meaning:
            Analyzes frequency-domain properties of the resonance,
            including center frequency, frequency span, and resolution,
            which are essential for BVP impedance characterization.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            Dict[str, float]: Frequency properties.
        """
        frequencies = peak_region["frequencies"]
        magnitude = peak_region["magnitude"]
        peak_idx = peak_region["peak_idx"]

        # Calculate frequency metrics
        center_frequency = frequencies[peak_idx]
        frequency_span = frequencies[-1] - frequencies[0]
        frequency_resolution = frequency_span / len(frequencies)

        return {
            "center_frequency": center_frequency,
            "frequency_span": frequency_span,
            "frequency_resolution": frequency_resolution,
        }

    def _analyze_amplitude_properties(
        self, peak_region: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Analyze amplitude properties.

        Physical Meaning:
            Analyzes amplitude characteristics of the resonance,
            including maximum, minimum, mean, and standard deviation,
            which provide insights into BVP impedance magnitude properties.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            Dict[str, float]: Amplitude properties.
        """
        magnitude = peak_region["magnitude"]

        # Calculate amplitude metrics
        max_amplitude = np.max(magnitude)
        min_amplitude = np.min(magnitude)
        mean_amplitude = np.mean(magnitude)
        std_amplitude = np.std(magnitude)

        return {
            "max_amplitude": max_amplitude,
            "min_amplitude": min_amplitude,
            "mean_amplitude": mean_amplitude,
            "std_amplitude": std_amplitude,
        }

    def _classify_resonance_type(self, peak_region: Dict[str, np.ndarray]) -> str:
        """
        Classify resonance type.

        Physical Meaning:
            Classifies the resonance type based on its characteristics,
            which helps in understanding the nature of BVP impedance
            variations and resonance behavior.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            str: Resonance type classification.
        """
        magnitude = peak_region["magnitude"]
        peak_idx = peak_region["peak_idx"]

        # Simple classification based on shape
        peak_amplitude = magnitude[peak_idx]
        mean_amplitude = np.mean(magnitude)

        if peak_amplitude > 2.0 * mean_amplitude:
            return "strong"
        elif peak_amplitude > 1.5 * mean_amplitude:
            return "moderate"
        else:
            return "weak"

    def _calculate_quality_factor_from_characteristics(
        self, resonance_shape: Dict[str, float], frequency_properties: Dict[str, float]
    ) -> float:
        """
        Calculate quality factor from resonance characteristics.

        Physical Meaning:
            Calculates the quality factor from resonance characteristics,
            which is a key parameter for characterizing BVP impedance
            resonance properties.

        Mathematical Foundation:
            Q = f_center / Δf, where f_center is the center frequency
            and Δf is the peak width.

        Args:
            resonance_shape (Dict[str, float]): Resonance shape characteristics.
            frequency_properties (Dict[str, float]): Frequency properties.

        Returns:
            float: Quality factor.
        """
        center_frequency = frequency_properties["center_frequency"]
        peak_width = resonance_shape["width"]

        quality_factor = center_frequency / peak_width if peak_width > 0 else 0.0
        return quality_factor

    def _calculate_peak_width(self, magnitude: np.ndarray, peak_idx: int) -> float:
        """
        Calculate peak width.

        Physical Meaning:
            Calculates the width of the resonance peak, which is
            essential for quality factor determination and
            resonance characterization.

        Args:
            magnitude (np.ndarray): Magnitude array.
            peak_idx (int): Peak index.

        Returns:
            float: Peak width.
        """
        peak_amplitude = magnitude[peak_idx]
        half_max = peak_amplitude / 2.0

        # Find indices where magnitude is above half maximum
        above_half_max = np.where(magnitude >= half_max)[0]

        if len(above_half_max) > 1:
            width = above_half_max[-1] - above_half_max[0]
        else:
            width = 1.0  # Fallback

        return float(width)

    def _calculate_peak_symmetry(self, magnitude: np.ndarray, peak_idx: int) -> float:
        """
        Calculate peak symmetry.

        Physical Meaning:
            Calculates the symmetry of the resonance peak, which
            provides insights into the linearity and quality of
            BVP impedance characteristics.

        Mathematical Foundation:
            Symmetry metric based on comparison of left and right
            sides of the peak, with 1.0 representing perfect symmetry.

        Args:
            magnitude (np.ndarray): Magnitude array.
            peak_idx (int): Peak index.

        Returns:
            float: Peak symmetry metric.
        """
        # Calculate symmetry by comparing left and right sides
        left_side = magnitude[:peak_idx]
        right_side = magnitude[peak_idx + 1 :]

        if len(left_side) == 0 or len(right_side) == 0:
            return 1.0  # Perfect symmetry if no sides

        # Calculate mean difference
        mean_left = np.mean(left_side)
        mean_right = np.mean(right_side)

        # Symmetry metric (1.0 = perfect symmetry)
        symmetry = 1.0 - abs(mean_left - mean_right) / (mean_left + mean_right)
        return max(0.0, min(1.0, symmetry))
