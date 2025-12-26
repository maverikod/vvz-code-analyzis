"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Comparison validation for beating analysis.

This module implements comparison validation functionality
for beating analysis results.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationComparison:
    """
    Comparison validation for beating analysis.

    Physical Meaning:
        Provides comparison validation functionality for
        beating analysis results.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize comparison validation analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.comparison_tolerance = 1e-3

    def compare_results(
        self, results1: Dict[str, Any], results2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare two sets of beating analysis results.

        Physical Meaning:
            Compares two sets of beating analysis results to
            identify differences and similarities.

        Args:
            results1 (Dict[str, Any]): First set of results.
            results2 (Dict[str, Any]): Second set of results.

        Returns:
            Dict[str, Any]: Comparison results.
        """
        comparison_results = {}

        # Compare beating frequencies
        if "beating_frequencies" in results1 and "beating_frequencies" in results2:
            freq_comparison = self._compare_beating_frequencies(
                results1["beating_frequencies"], results2["beating_frequencies"]
            )
            comparison_results["frequency_comparison"] = freq_comparison

        # Compare interference patterns
        if "interference_patterns" in results1 and "interference_patterns" in results2:
            pattern_comparison = self._compare_interference_patterns(
                results1["interference_patterns"], results2["interference_patterns"]
            )
            comparison_results["pattern_comparison"] = pattern_comparison

        # Compare mode coupling
        if "mode_coupling" in results1 and "mode_coupling" in results2:
            coupling_comparison = self._compare_mode_coupling(
                results1["mode_coupling"], results2["mode_coupling"]
            )
            comparison_results["coupling_comparison"] = coupling_comparison

        # Compute overall comparison
        overall_comparison = self._compute_overall_comparison(comparison_results)
        comparison_results["overall_comparison"] = overall_comparison

        return comparison_results

    def _compare_beating_frequencies(
        self, freq1: List[float], freq2: List[float]
    ) -> Dict[str, Any]:
        """Compare beating frequencies between two analyses."""
        if not freq1 and not freq2:
            return {"similarity": 1.0, "difference": 0.0}

        if not freq1 or not freq2:
            return {"similarity": 0.0, "difference": 1.0}

        # Calculate mean frequencies
        mean1 = np.mean(freq1)
        mean2 = np.mean(freq2)

        # Calculate similarity
        freq_diff = abs(mean1 - mean2)
        relative_diff = freq_diff / max(mean1, mean2) if max(mean1, mean2) > 0 else 0
        similarity = max(0.0, 1.0 - relative_diff)

        return {
            "similarity": similarity,
            "difference": relative_diff,
            "mean_frequency_1": mean1,
            "mean_frequency_2": mean2,
        }

    def _compare_interference_patterns(
        self, patterns1: List[Dict[str, Any]], patterns2: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compare interference patterns between two analyses."""
        if not patterns1 and not patterns2:
            return {"similarity": 1.0, "difference": 0.0}

        if not patterns1 or not patterns2:
            return {"similarity": 0.0, "difference": 1.0}

        # Compare pattern counts
        count_diff = abs(len(patterns1) - len(patterns2))
        count_similarity = 1.0 - (count_diff / max(len(patterns1), len(patterns2)))

        return {
            "similarity": count_similarity,
            "difference": 1.0 - count_similarity,
            "pattern_count_1": len(patterns1),
            "pattern_count_2": len(patterns2),
        }

    def _compare_mode_coupling(
        self, coupling1: Dict[str, Any], coupling2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare mode coupling between two analyses."""
        strength1 = coupling1.get("coupling_strength", 0.0)
        strength2 = coupling2.get("coupling_strength", 0.0)

        strength_diff = abs(strength1 - strength2)
        similarity = max(0.0, 1.0 - strength_diff)

        return {
            "similarity": similarity,
            "difference": strength_diff,
            "coupling_strength_1": strength1,
            "coupling_strength_2": strength2,
        }

    def _compute_overall_comparison(
        self, comparison_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compute overall comparison metrics."""
        similarities = []
        for key, result in comparison_results.items():
            if isinstance(result, dict) and "similarity" in result:
                similarities.append(result["similarity"])

        if not similarities:
            return {"overall_similarity": 0.0, "comparison_quality": "poor"}

        overall_similarity = np.mean(similarities)

        if overall_similarity > 0.8:
            comparison_quality = "excellent"
        elif overall_similarity > 0.6:
            comparison_quality = "good"
        elif overall_similarity > 0.4:
            comparison_quality = "fair"
        else:
            comparison_quality = "poor"

        return {
            "overall_similarity": overall_similarity,
            "comparison_quality": comparison_quality,
            "number_of_comparisons": len(similarities),
        }
