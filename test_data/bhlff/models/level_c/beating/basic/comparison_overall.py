"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Overall comparison functionality for beating analysis.

This module implements overall comparison functionality
for analyzing mode beating in the 7D phase field according to the
theoretical framework.

Physical Meaning:
    Implements overall comparison of beating analysis results
    to calculate similarity, consistency, and comparison results.

Example:
    >>> comparator = OverallComparator()
    >>> results = comparator.calculate_overall_comparison(comparisons)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging


class OverallComparator:
    """
    Overall comparison for beating analysis.

    Physical Meaning:
        Calculates overall comparison between
        beating analysis results.

    Mathematical Foundation:
        Implements overall comparison methods:
        - Similarity calculation across all aspects
        - Consistency assessment
        - Comparison result determination
    """

    def __init__(
        self, similarity_threshold: float = 0.8, consistency_threshold: float = 0.9
    ):
        """
        Initialize overall comparator.

        Args:
            similarity_threshold (float): Threshold for similarity assessment.
            consistency_threshold (float): Threshold for consistency assessment.
        """
        self.logger = logging.getLogger(__name__)
        self.similarity_threshold = similarity_threshold
        self.consistency_threshold = consistency_threshold

    def calculate_overall_comparison(
        self,
        basic_comparison: Dict[str, Any],
        interference_comparison: Dict[str, Any],
        coupling_comparison: Dict[str, Any],
        phase_comparison: Dict[str, Any],
        frequency_comparison: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate overall comparison.

        Physical Meaning:
            Calculates the overall comparison between
            two analysis results.

        Args:
            basic_comparison (Dict[str, Any]): Basic analysis comparison.
            interference_comparison (Dict[str, Any]): Interference comparison.
            coupling_comparison (Dict[str, Any]): Coupling comparison.
            phase_comparison (Dict[str, Any]): Phase comparison.
            frequency_comparison (Dict[str, Any]): Frequency comparison.

        Returns:
            Dict[str, Any]: Overall comparison.
        """
        # Calculate overall similarity
        overall_similarity = np.mean(
            [
                basic_comparison["similarity"],
                interference_comparison["overall_similarity"],
                coupling_comparison["overall_similarity"],
                phase_comparison["overall_similarity"],
                frequency_comparison["overall_similarity"],
            ]
        )

        # Calculate overall consistency
        overall_consistency = self._calculate_consistency(
            basic_comparison,
            interference_comparison,
            coupling_comparison,
            phase_comparison,
            frequency_comparison,
        )

        # Determine comparison result
        if overall_similarity > self.similarity_threshold:
            comparison_result = "highly_similar"
        elif overall_similarity > 0.5:
            comparison_result = "moderately_similar"
        else:
            comparison_result = "different"

        return {
            "overall_similarity": overall_similarity,
            "overall_consistency": overall_consistency,
            "comparison_result": comparison_result,
            "are_consistent": overall_consistency > self.consistency_threshold,
        }

    def _calculate_consistency(
        self,
        basic_comparison: Dict[str, Any],
        interference_comparison: Dict[str, Any],
        coupling_comparison: Dict[str, Any],
        phase_comparison: Dict[str, Any],
        frequency_comparison: Dict[str, Any],
    ) -> float:
        """
        Calculate consistency.

        Physical Meaning:
            Calculates the consistency between
            different aspects of the analysis.

        Args:
            basic_comparison (Dict[str, Any]): Basic analysis comparison.
            interference_comparison (Dict[str, Any]): Interference comparison.
            coupling_comparison (Dict[str, Any]): Coupling comparison.
            phase_comparison (Dict[str, Any]): Phase comparison.
            frequency_comparison (Dict[str, Any]): Frequency comparison.

        Returns:
            float: Consistency score.
        """
        # Calculate consistency based on similarity across all aspects
        similarities = [
            basic_comparison["similarity"],
            interference_comparison["overall_similarity"],
            coupling_comparison["overall_similarity"],
            phase_comparison["overall_similarity"],
            frequency_comparison["overall_similarity"],
        ]

        # Calculate consistency as inverse of variance
        consistency = 1.0 - np.var(similarities)

        return float(consistency)
