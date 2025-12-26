"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Metrics comparison functionality for beating analysis.

This module implements metrics comparison functionality
for analyzing mode beating in the 7D phase field according to the
theoretical framework.

Physical Meaning:
    Implements comparison of metrics between beating analysis results
    to identify differences and similarities.

Example:
    >>> comparator = MetricsComparator()
    >>> results = comparator.compare_metrics(metrics1, metrics2)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging


class MetricsComparator:
    """
    Metrics comparison for beating analysis.

    Physical Meaning:
        Compares metrics between beating analysis results
        to identify differences and similarities.

    Mathematical Foundation:
        Implements comparison methods for metrics:
        - Statistical comparison of metrics
        - Relative difference calculation
        - Similarity assessment
    """

    def __init__(self):
        """Initialize metrics comparator."""
        self.logger = logging.getLogger(__name__)

    def compare_metrics(
        self, metrics1: Dict[str, Any], metrics2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare metrics between two analyses.

        Physical Meaning:
            Compares specific metrics between two
            analysis results.

        Args:
            metrics1 (Dict[str, Any]): First analysis metrics.
            metrics2 (Dict[str, Any]): Second analysis metrics.

        Returns:
            Dict[str, Any]: Metrics comparison.
        """
        # Compare amplitude metrics
        amplitude_comparison = self._compare_amplitude_metrics(metrics1, metrics2)

        # Compare energy metrics
        energy_comparison = self._compare_energy_metrics(metrics1, metrics2)

        # Compare variance metrics
        variance_comparison = self._compare_variance_metrics(metrics1, metrics2)

        return {
            "amplitude_comparison": amplitude_comparison,
            "energy_comparison": energy_comparison,
            "variance_comparison": variance_comparison,
        }

    def _compare_amplitude_metrics(
        self, metrics1: Dict[str, Any], metrics2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare amplitude metrics.

        Physical Meaning:
            Compares amplitude-related metrics between
            two analysis results.

        Args:
            metrics1 (Dict[str, Any]): First analysis metrics.
            metrics2 (Dict[str, Any]): Second analysis metrics.

        Returns:
            Dict[str, Any]: Amplitude metrics comparison.
        """
        # Extract amplitude metrics
        mean_amp1 = metrics1.get("mean_amplitude", 0.0)
        mean_amp2 = metrics2.get("mean_amplitude", 0.0)
        max_amp1 = metrics1.get("max_amplitude", 0.0)
        max_amp2 = metrics2.get("max_amplitude", 0.0)
        min_amp1 = metrics1.get("min_amplitude", 0.0)
        min_amp2 = metrics2.get("min_amplitude", 0.0)

        # Calculate differences
        mean_diff = abs(mean_amp1 - mean_amp2)
        max_diff = abs(max_amp1 - max_amp2)
        min_diff = abs(min_amp1 - min_amp2)

        # Calculate relative differences
        mean_rel_diff = mean_diff / (mean_amp1 + mean_amp2 + 1e-12)
        max_rel_diff = max_diff / (max_amp1 + max_amp2 + 1e-12)
        min_rel_diff = min_diff / (min_amp1 + min_amp2 + 1e-12)

        return {
            "mean_difference": mean_diff,
            "max_difference": max_diff,
            "min_difference": min_diff,
            "mean_relative_difference": mean_rel_diff,
            "max_relative_difference": max_rel_diff,
            "min_relative_difference": min_rel_diff,
        }

    def _compare_energy_metrics(
        self, metrics1: Dict[str, Any], metrics2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare energy metrics.

        Physical Meaning:
            Compares energy-related metrics between
            two analysis results.

        Args:
            metrics1 (Dict[str, Any]): First analysis metrics.
            metrics2 (Dict[str, Any]): Second analysis metrics.

        Returns:
            Dict[str, Any]: Energy metrics comparison.
        """
        # Extract energy metrics
        energy1 = metrics1.get("field_energy", 0.0)
        energy2 = metrics2.get("field_energy", 0.0)

        # Calculate differences
        energy_diff = abs(energy1 - energy2)
        energy_rel_diff = energy_diff / (energy1 + energy2 + 1e-12)

        return {
            "energy_difference": energy_diff,
            "energy_relative_difference": energy_rel_diff,
        }

    def _compare_variance_metrics(
        self, metrics1: Dict[str, Any], metrics2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare variance metrics.

        Physical Meaning:
            Compares variance-related metrics between
            two analysis results.

        Args:
            metrics1 (Dict[str, Any]): First analysis metrics.
            metrics2 (Dict[str, Any]): Second analysis metrics.

        Returns:
            Dict[str, Any]: Variance metrics comparison.
        """
        # Extract variance metrics
        variance1 = metrics1.get("spatial_variance", 0.0)
        variance2 = metrics2.get("spatial_variance", 0.0)

        # Calculate differences
        variance_diff = abs(variance1 - variance2)
        variance_rel_diff = variance_diff / (variance1 + variance2 + 1e-12)

        return {
            "variance_difference": variance_diff,
            "variance_relative_difference": variance_rel_diff,
        }

    def calculate_similarity(self, comparison_metrics: Dict[str, Any]) -> float:
        """
        Calculate similarity between analyses.

        Physical Meaning:
            Calculates the overall similarity between
            two analysis results.

        Args:
            comparison_metrics (Dict[str, Any]): Comparison metrics.

        Returns:
            float: Similarity score.
        """
        # Calculate similarity based on relative differences
        amplitude_sim = (
            1.0 - comparison_metrics["amplitude_comparison"]["mean_relative_difference"]
        )
        energy_sim = (
            1.0 - comparison_metrics["energy_comparison"]["energy_relative_difference"]
        )
        variance_sim = (
            1.0
            - comparison_metrics["variance_comparison"]["variance_relative_difference"]
        )

        # Calculate overall similarity
        overall_similarity = np.mean([amplitude_sim, energy_sim, variance_sim])

        return float(overall_similarity)

    def calculate_differences(
        self, comparison_metrics: Dict[str, Any], difference_threshold: float = 0.2
    ) -> Dict[str, Any]:
        """
        Calculate differences between analyses.

        Physical Meaning:
            Calculates the differences between
            two analysis results.

        Args:
            comparison_metrics (Dict[str, Any]): Comparison metrics.
            difference_threshold (float): Threshold for significant differences.

        Returns:
            Dict[str, Any]: Differences analysis.
        """
        # Calculate overall differences
        overall_difference = np.mean(
            [
                comparison_metrics["amplitude_comparison"]["mean_relative_difference"],
                comparison_metrics["energy_comparison"]["energy_relative_difference"],
                comparison_metrics["variance_comparison"][
                    "variance_relative_difference"
                ],
            ]
        )

        # Determine difference level
        if overall_difference < 0.1:
            difference_level = "minimal"
        elif overall_difference < 0.3:
            difference_level = "moderate"
        else:
            difference_level = "significant"

        return {
            "overall_difference": overall_difference,
            "difference_level": difference_level,
            "are_different": overall_difference > difference_threshold,
        }
