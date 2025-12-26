"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic comparison for beating analysis.

This module implements comparison functionality for analyzing
differences between beating analysis results.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class BeatingBasicComparison:
    """
    Basic comparison for beating analysis.

    Physical Meaning:
        Provides comparison functionality for analyzing
        differences between beating analysis results.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize comparison analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def compare_analyses(
        self, results1: Dict[str, Any], results2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare two beating analysis results.

        Physical Meaning:
            Compares two sets of beating analysis results to
            identify differences, similarities, and consistency.

        Args:
            results1 (Dict[str, Any]): First analysis results.
            results2 (Dict[str, Any]): Second analysis results.

        Returns:
            Dict[str, Any]: Comparison results.
        """
        self.logger.info("Starting analysis comparison")

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

        self.logger.info("Analysis comparison completed")
        return comparison_results

    def _compare_beating_frequencies(
        self, freq1: List[float], freq2: List[float]
    ) -> Dict[str, Any]:
        """
        Compare beating frequencies between two analyses.

        Physical Meaning:
            Compares beating frequencies to identify
            similarities and differences in frequency content.

        Args:
            freq1 (List[float]): First set of frequencies.
            freq2 (List[float]): Second set of frequencies.

        Returns:
            Dict[str, Any]: Frequency comparison results.
        """
        if not freq1 and not freq2:
            return {"similarity": 1.0, "difference": 0.0, "common_frequencies": 0}

        if not freq1 or not freq2:
            return {"similarity": 0.0, "difference": 1.0, "common_frequencies": 0}

        # Convert to arrays
        freq1_array = np.array(freq1)
        freq2_array = np.array(freq2)

        # Calculate mean frequencies
        mean1 = np.mean(freq1_array)
        mean2 = np.mean(freq2_array)

        # Calculate frequency differences
        freq_diff = abs(mean1 - mean2)
        relative_diff = freq_diff / max(mean1, mean2) if max(mean1, mean2) > 0 else 0

        # Calculate similarity
        similarity = max(0.0, 1.0 - relative_diff)

        # Count common frequencies (within 10% tolerance)
        tolerance = 0.1
        common_count = 0
        for f1 in freq1:
            for f2 in freq2:
                if abs(f1 - f2) / max(f1, f2) <= tolerance:
                    common_count += 1
                    break

        return {
            "similarity": similarity,
            "difference": relative_diff,
            "common_frequencies": common_count,
            "mean_frequency_1": mean1,
            "mean_frequency_2": mean2,
            "frequency_difference": freq_diff,
        }

    def _compare_interference_patterns(
        self, patterns1: List[Dict[str, Any]], patterns2: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare interference patterns between two analyses.

        Physical Meaning:
            Compares interference patterns to identify
            similarities and differences in pattern characteristics.

        Args:
            patterns1 (List[Dict[str, Any]]): First set of patterns.
            patterns2 (List[Dict[str, Any]]): Second set of patterns.

        Returns:
            Dict[str, Any]: Pattern comparison results.
        """
        if not patterns1 and not patterns2:
            return {"similarity": 1.0, "difference": 0.0, "pattern_count_diff": 0}

        if not patterns1 or not patterns2:
            return {
                "similarity": 0.0,
                "difference": 1.0,
                "pattern_count_diff": abs(len(patterns1) - len(patterns2)),
            }

        # Compare pattern counts
        count_diff = abs(len(patterns1) - len(patterns2))
        count_similarity = 1.0 - (count_diff / max(len(patterns1), len(patterns2)))

        # Compare pattern strengths
        strengths1 = [p.get("strength", 0.0) for p in patterns1]
        strengths2 = [p.get("strength", 0.0) for p in patterns2]

        if strengths1 and strengths2:
            mean_strength1 = np.mean(strengths1)
            mean_strength2 = np.mean(strengths2)
            strength_diff = (
                abs(mean_strength1 - mean_strength2)
                / max(mean_strength1, mean_strength2)
                if max(mean_strength1, mean_strength2) > 0
                else 0
            )
            strength_similarity = max(0.0, 1.0 - strength_diff)
        else:
            strength_similarity = 0.0
            strength_diff = 1.0

        # Overall similarity
        overall_similarity = (count_similarity + strength_similarity) / 2

        return {
            "similarity": overall_similarity,
            "difference": 1.0 - overall_similarity,
            "pattern_count_diff": count_diff,
            "strength_similarity": strength_similarity,
            "count_similarity": count_similarity,
        }

    def _compare_mode_coupling(
        self, coupling1: Dict[str, Any], coupling2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare mode coupling between two analyses.

        Physical Meaning:
            Compares mode coupling characteristics to identify
            similarities and differences in coupling behavior.

        Args:
            coupling1 (Dict[str, Any]): First coupling analysis.
            coupling2 (Dict[str, Any]): Second coupling analysis.

        Returns:
            Dict[str, Any]: Coupling comparison results.
        """
        # Compare coupling strength
        strength1 = coupling1.get("coupling_strength", 0.0)
        strength2 = coupling2.get("coupling_strength", 0.0)
        strength_diff = abs(strength1 - strength2)
        strength_similarity = max(0.0, 1.0 - strength_diff)

        # Compare coupling efficiency
        efficiency1 = coupling1.get("coupling_efficiency", 0.0)
        efficiency2 = coupling2.get("coupling_efficiency", 0.0)
        efficiency_diff = abs(efficiency1 - efficiency2)
        efficiency_similarity = max(0.0, 1.0 - efficiency_diff)

        # Compare coupling type
        type1 = coupling1.get("coupling_type", "unknown")
        type2 = coupling2.get("coupling_type", "unknown")
        type_similarity = 1.0 if type1 == type2 else 0.0

        # Overall similarity
        overall_similarity = (
            strength_similarity + efficiency_similarity + type_similarity
        ) / 3

        return {
            "similarity": overall_similarity,
            "difference": 1.0 - overall_similarity,
            "strength_similarity": strength_similarity,
            "efficiency_similarity": efficiency_similarity,
            "type_similarity": type_similarity,
            "strength_difference": strength_diff,
            "efficiency_difference": efficiency_diff,
        }

    def _compute_overall_comparison(
        self, comparison_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute overall comparison metrics.

        Physical Meaning:
            Computes overall comparison metrics from individual
            comparison results to provide a summary assessment.

        Args:
            comparison_results (Dict[str, Any]): Individual comparison results.

        Returns:
            Dict[str, Any]: Overall comparison results.
        """
        similarities = []
        differences = []

        # Collect similarities and differences
        for key, result in comparison_results.items():
            if isinstance(result, dict):
                if "similarity" in result:
                    similarities.append(result["similarity"])
                if "difference" in result:
                    differences.append(result["difference"])

        # Calculate overall metrics
        if similarities:
            overall_similarity = np.mean(similarities)
            overall_difference = (
                np.mean(differences) if differences else 1.0 - overall_similarity
            )
        else:
            overall_similarity = 0.0
            overall_difference = 1.0

        # Determine comparison quality
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
            "overall_difference": overall_difference,
            "comparison_quality": comparison_quality,
            "number_of_comparisons": len(similarities),
            "consistency_score": (
                1.0 - np.std(similarities) if len(similarities) > 1 else 1.0
            ),
        }
