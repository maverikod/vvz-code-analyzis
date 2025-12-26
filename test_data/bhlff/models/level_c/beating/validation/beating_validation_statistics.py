"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical validation for beating analysis.

This module implements statistical validation functionality
for beating analysis results.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationStatistics:
    """
    Statistical validation for beating analysis.

    Physical Meaning:
        Provides statistical validation functionality for
        beating analysis results.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize statistical validation analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.statistical_significance = 0.05

    def compute_overall_statistical_validation(
        self, validation_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute overall statistical validation.

        Physical Meaning:
            Computes overall statistical validation metrics
            from individual validation results.

        Args:
            validation_results (Dict[str, Any]): Individual validation results.

        Returns:
            Dict[str, Any]: Overall statistical validation results.
        """
        # Collect validation scores
        validation_scores = []
        for key, result in validation_results.items():
            if isinstance(result, dict) and "confidence" in result:
                validation_scores.append(result["confidence"])

        if not validation_scores:
            return {
                "overall_confidence": 0.0,
                "validation_passed": False,
                "statistical_significance": self.statistical_significance,
            }

        # Calculate overall metrics
        overall_confidence = np.mean(validation_scores)
        validation_passed = overall_confidence > 0.5

        return {
            "overall_confidence": overall_confidence,
            "validation_passed": validation_passed,
            "statistical_significance": self.statistical_significance,
            "number_of_validations": len(validation_scores),
            "confidence_std": (
                np.std(validation_scores) if len(validation_scores) > 1 else 0.0
            ),
        }
