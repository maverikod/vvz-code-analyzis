"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonance statistics for BVP impedance analysis.

This module implements statistical analysis methods for resonance quality factors,
including comparison methods and significance testing.
"""

import numpy as np
from typing import List, Dict, Tuple

from ..bvp_constants import BVPConstants


class ResonanceStatistics:
    """
    Resonance statistics for BVP impedance analysis.

    Physical Meaning:
        Provides statistical analysis methods for resonance quality factors,
        including comparison methods, significance testing, and
        distribution analysis for BVP impedance characterization.

    Mathematical Foundation:
        Uses statistical methods to analyze quality factor distributions,
        including mean differences, standard deviations, correlations,
        and significance testing for resonance comparison.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize resonance statistics analyzer.

        Physical Meaning:
            Sets up the statistics analyzer with BVP constants for
            statistical analysis of resonance properties.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants

    def compare_quality_factors(
        self, quality_factors_1: List[float], quality_factors_2: List[float]
    ) -> Dict[str, float]:
        """
        Compare quality factors between two sets of resonances.

        Physical Meaning:
            Compares quality factors between two sets of resonances
            to analyze differences in resonance characteristics and
            identify systematic variations in BVP impedance properties.

        Mathematical Foundation:
            Uses statistical methods to compare quality factor distributions:
            - Mean difference: μ₁ - μ₂
            - Standard deviation difference: √(σ₁² + σ₂²)
            - Correlation coefficient: ρ(Q₁, Q₂)
            - Significance: |μ₁ - μ₂| / σ_diff

        Args:
            quality_factors_1 (List[float]): First set of quality factors.
            quality_factors_2 (List[float]): Second set of quality factors.

        Returns:
            Dict[str, float]: Comparison results.
        """
        if not quality_factors_1 or not quality_factors_2:
            return {
                "mean_difference": 0.0,
                "std_difference": 0.0,
                "correlation": 0.0,
                "significance": 0.0,
            }

        # Calculate statistics
        mean_1 = np.mean(quality_factors_1)
        mean_2 = np.mean(quality_factors_2)
        std_1 = np.std(quality_factors_1)
        std_2 = np.std(quality_factors_2)

        # Calculate differences
        mean_difference = mean_1 - mean_2
        std_difference = np.sqrt(std_1**2 + std_2**2)

        # Calculate correlation
        correlation = self._calculate_correlation(quality_factors_1, quality_factors_2)

        # Calculate significance (simplified)
        significance = (
            abs(mean_difference) / std_difference if std_difference > 0 else 0.0
        )

        return {
            "mean_difference": mean_difference,
            "std_difference": std_difference,
            "correlation": correlation,
            "significance": significance,
        }

    def analyze_quality_factor_distribution(
        self, quality_factors: List[float]
    ) -> Dict[str, float]:
        """
        Analyze quality factor distribution.

        Physical Meaning:
            Analyzes the statistical distribution of quality factors
            to understand the variability and characteristics of
            BVP impedance resonance properties.

        Mathematical Foundation:
            Calculates statistical moments of the quality factor distribution:
            - Mean: μ = (1/n) Σ Q_i
            - Standard deviation: σ = √((1/n) Σ (Q_i - μ)²)
            - Skewness: measure of asymmetry
            - Kurtosis: measure of tail heaviness

        Args:
            quality_factors (List[float]): List of quality factors.

        Returns:
            Dict[str, float]: Distribution statistics.
        """
        if not quality_factors:
            return {
                "mean": 0.0,
                "std": 0.0,
                "skewness": 0.0,
                "kurtosis": 0.0,
                "min": 0.0,
                "max": 0.0,
            }

        qf_array = np.array(quality_factors)

        # Calculate basic statistics
        mean = np.mean(qf_array)
        std = np.std(qf_array)
        min_val = np.min(qf_array)
        max_val = np.max(qf_array)

        # Calculate higher moments
        skewness = self._calculate_skewness(qf_array, mean, std)
        kurtosis = self._calculate_kurtosis(qf_array, mean, std)

        return {
            "mean": mean,
            "std": std,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "min": min_val,
            "max": max_val,
        }

    def _calculate_correlation(self, qf1: List[float], qf2: List[float]) -> float:
        """
        Calculate correlation between two quality factor sets.

        Physical Meaning:
            Calculates the correlation coefficient between two sets
            of quality factors to assess their relationship.

        Mathematical Foundation:
            ρ = Σ((Q₁ᵢ - μ₁)(Q₂ᵢ - μ₂)) / (n σ₁ σ₂)
            where μ and σ are mean and standard deviation.

        Args:
            qf1 (List[float]): First set of quality factors.
            qf2 (List[float]): Second set of quality factors.

        Returns:
            float: Correlation coefficient.
        """
        if len(qf1) != len(qf2) or len(qf1) < 2:
            return 0.0

        correlation = np.corrcoef(qf1, qf2)[0, 1]
        return correlation if not np.isnan(correlation) else 0.0

    def _calculate_skewness(self, data: np.ndarray, mean: float, std: float) -> float:
        """
        Calculate skewness of the distribution.

        Physical Meaning:
            Calculates the skewness (third moment) of the quality factor
            distribution to assess asymmetry.

        Mathematical Foundation:
            Skewness = (1/n) Σ ((x_i - μ) / σ)³

        Args:
            data (np.ndarray): Data array.
            mean (float): Mean value.
            std (float): Standard deviation.

        Returns:
            float: Skewness value.
        """
        if std == 0:
            return 0.0

        normalized = (data - mean) / std
        skewness = np.mean(normalized**3)
        return skewness

    def _calculate_kurtosis(self, data: np.ndarray, mean: float, std: float) -> float:
        """
        Calculate kurtosis of the distribution.

        Physical Meaning:
            Calculates the kurtosis (fourth moment) of the quality factor
            distribution to assess tail heaviness.

        Mathematical Foundation:
            Kurtosis = (1/n) Σ ((x_i - μ) / σ)⁴ - 3
            (excess kurtosis, where 3 is subtracted for normal distribution)

        Args:
            data (np.ndarray): Data array.
            mean (float): Mean value.
            std (float): Standard deviation.

        Returns:
            float: Kurtosis value.
        """
        if std == 0:
            return 0.0

        normalized = (data - mean) / std
        kurtosis = np.mean(normalized**4) - 3.0  # Excess kurtosis
        return kurtosis
