"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Accuracy optimization for beating validation.

This module implements accuracy optimization functionality
for beating validation.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationAccuracyOptimization:
    """
    Accuracy optimization for beating validation.

    Physical Meaning:
        Provides accuracy optimization functionality for
        beating validation.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize accuracy optimization analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def optimize_accuracy(
        self, results: Dict[str, Any], initial_accuracy: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Optimize validation accuracy.

        Physical Meaning:
            Optimizes validation accuracy to improve reliability
            of validation.

        Args:
            results (Dict[str, Any]): Analysis results.
            initial_accuracy (Dict[str, float]): Initial accuracy parameters.

        Returns:
            Dict[str, float]: Optimized accuracy parameters.
        """
        optimized_accuracy = initial_accuracy.copy()

        # Optimize tolerance based on result complexity
        complexity = self._assess_complexity(results)

        # Adjust tolerance based on complexity
        if complexity > 0.8:
            optimized_accuracy["tolerance"] = (
                1e-4  # Stricter tolerance for high complexity
            )
        elif complexity > 0.5:
            optimized_accuracy["tolerance"] = (
                1e-3  # Moderate tolerance for medium complexity
            )
        else:
            optimized_accuracy["tolerance"] = (
                1e-2  # Relaxed tolerance for low complexity
            )

        # Adjust confidence threshold
        if complexity > 0.7:
            optimized_accuracy["confidence_threshold"] = (
                0.9  # Higher confidence for high complexity
            )
        else:
            optimized_accuracy["confidence_threshold"] = 0.8  # Standard confidence

        # Adjust statistical significance
        if complexity > 0.6:
            optimized_accuracy["statistical_significance"] = (
                0.01  # More stringent for high complexity
            )
        else:
            optimized_accuracy["statistical_significance"] = (
                0.05  # Standard significance
            )

        return optimized_accuracy

    def validate_optimization(
        self,
        results: Dict[str, Any],
        initial_accuracy: Dict[str, float],
        optimized_accuracy: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Validate accuracy optimization.

        Physical Meaning:
            Validates that accuracy optimization improves
            validation reliability.

        Args:
            results (Dict[str, Any]): Analysis results.
            initial_accuracy (Dict[str, float]): Initial accuracy.
            optimized_accuracy (Dict[str, float]): Optimized accuracy.

        Returns:
            Dict[str, Any]: Validation results.
        """
        # Calculate accuracy metrics
        initial_accuracy_score = self._calculate_accuracy_score(
            results, initial_accuracy
        )
        optimized_accuracy_score = self._calculate_accuracy_score(
            results, optimized_accuracy
        )

        improvement = optimized_accuracy_score - initial_accuracy_score
        improvement_percentage = (
            (improvement / initial_accuracy_score) * 100
            if initial_accuracy_score > 0
            else 0
        )

        return {
            "initial_accuracy_score": initial_accuracy_score,
            "optimized_accuracy_score": optimized_accuracy_score,
            "improvement": improvement,
            "improvement_percentage": improvement_percentage,
            "optimization_successful": improvement > 0,
        }

    def _assess_complexity(self, results: Dict[str, Any]) -> float:
        """Assess complexity of analysis results."""
        complexity_factors = []

        # Check frequency complexity
        if "beating_frequencies" in results:
            frequencies = results["beating_frequencies"]
            if isinstance(frequencies, list):
                freq_complexity = min(1.0, len(frequencies) / 10.0)
                complexity_factors.append(freq_complexity)

        # Check pattern complexity
        if "interference_patterns" in results:
            patterns = results["interference_patterns"]
            if isinstance(patterns, list):
                pattern_complexity = min(1.0, len(patterns) / 5.0)
                complexity_factors.append(pattern_complexity)

        # Check coupling complexity
        if "mode_coupling" in results:
            coupling = results["mode_coupling"]
            if isinstance(coupling, dict):
                coupling_strength = coupling.get("coupling_strength", 0.0)
                complexity_factors.append(coupling_strength)

        # Calculate overall complexity
        if complexity_factors:
            overall_complexity = np.mean(complexity_factors)
        else:
            overall_complexity = 0.5  # Default moderate complexity

        return min(1.0, overall_complexity)

    def _calculate_accuracy_score(
        self, results: Dict[str, Any], accuracy_params: Dict[str, float]
    ) -> float:
        """Calculate accuracy score for given parameters."""
        # Base accuracy score
        accuracy_score = 0.5

        # Adjust based on tolerance
        tolerance = accuracy_params.get("tolerance", 1e-3)
        if tolerance < 1e-4:
            accuracy_score += 0.3  # High accuracy for strict tolerance
        elif tolerance < 1e-2:
            accuracy_score += 0.2  # Medium accuracy for moderate tolerance
        else:
            accuracy_score += 0.1  # Low accuracy for relaxed tolerance

        # Adjust based on confidence threshold
        confidence_threshold = accuracy_params.get("confidence_threshold", 0.8)
        if confidence_threshold > 0.9:
            accuracy_score += 0.2  # High accuracy for high confidence
        elif confidence_threshold > 0.8:
            accuracy_score += 0.1  # Medium accuracy for standard confidence

        # Adjust based on statistical significance
        significance = accuracy_params.get("statistical_significance", 0.05)
        if significance < 0.01:
            accuracy_score += 0.2  # High accuracy for strict significance
        elif significance < 0.05:
            accuracy_score += 0.1  # Medium accuracy for standard significance

        return min(1.0, accuracy_score)
