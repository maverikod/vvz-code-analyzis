"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating comparison module.

This module implements comparison functionality
for analyzing mode beating in the 7D phase field according to the
theoretical framework.

Physical Meaning:
    Implements comparison of beating analysis results
    to identify differences, similarities, and consistency.

Example:
    >>> comparator = BeatingComparator(bvp_core)
    >>> results = comparator.compare_analyses(results1, results2)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .comparison_metrics import MetricsComparator
from .comparison_patterns import PatternComparator
from .comparison_overall import OverallComparator


class BeatingComparator:
    """
    Beating comparison for Level C.

    Physical Meaning:
        Compares beating analysis results to identify
        differences, similarities, and consistency.

    Mathematical Foundation:
        Implements comparison methods for beating analysis:
        - Statistical comparison of results
        - Pattern similarity analysis
        - Consistency validation
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating comparator.

        Physical Meaning:
            Sets up the comparison system with
            comparison parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Comparison parameters
        self.similarity_threshold = 0.8
        self.difference_threshold = 0.2
        self.consistency_threshold = 0.9

        # Initialize comparison components
        self._metrics_comparator = MetricsComparator()
        self._pattern_comparator = PatternComparator()
        self._overall_comparator = OverallComparator(
            self.similarity_threshold, self.consistency_threshold
        )

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
        self.logger.info("Starting beating analysis comparison")

        # Compare basic analysis
        basic_comparison = self._compare_basic_analysis(results1, results2)

        # Compare interference patterns
        interference_comparison = (
            self._pattern_comparator.compare_interference_patterns(results1, results2)
        )

        # Compare mode coupling
        coupling_comparison = self._pattern_comparator.compare_mode_coupling(
            results1, results2
        )

        # Compare phase coherence
        phase_comparison = self._pattern_comparator.compare_phase_coherence(
            results1, results2
        )

        # Compare beating frequencies
        frequency_comparison = self._pattern_comparator.compare_beating_frequencies(
            results1, results2
        )

        # Calculate overall comparison
        overall_comparison = self._overall_comparator.calculate_overall_comparison(
            basic_comparison,
            interference_comparison,
            coupling_comparison,
            phase_comparison,
            frequency_comparison,
        )

        # Combine all comparison results
        comparison_results = {
            "basic_comparison": basic_comparison,
            "interference_comparison": interference_comparison,
            "coupling_comparison": coupling_comparison,
            "phase_comparison": phase_comparison,
            "frequency_comparison": frequency_comparison,
            "overall_comparison": overall_comparison,
            "comparison_complete": True,
        }

        self.logger.info("Beating analysis comparison completed")
        return comparison_results

    def _compare_basic_analysis(
        self, results1: Dict[str, Any], results2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare basic analysis results.

        Physical Meaning:
            Compares basic analysis results between
            two analysis runs.

        Args:
            results1 (Dict[str, Any]): First analysis results.
            results2 (Dict[str, Any]): Second analysis results.

        Returns:
            Dict[str, Any]: Basic analysis comparison.
        """
        # Extract basic analysis results
        basic1 = results1.get("basic_analysis", {})
        basic2 = results2.get("basic_analysis", {})

        # Compare metrics
        comparison_metrics = self._metrics_comparator.compare_metrics(basic1, basic2)

        # Calculate similarity
        similarity = self._metrics_comparator.calculate_similarity(comparison_metrics)

        # Calculate differences
        differences = self._metrics_comparator.calculate_differences(
            comparison_metrics, self.difference_threshold
        )

        return {
            "comparison_metrics": comparison_metrics,
            "similarity": similarity,
            "differences": differences,
            "are_similar": similarity > self.similarity_threshold,
        }
