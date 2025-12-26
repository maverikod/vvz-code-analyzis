"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical analysis validation for beating.
"""

import numpy as np
from typing import Dict, Any

from .beating_basic_core_validation_quality import BeatingCoreValidationQuality


class BeatingCoreValidationStatistical:
    """
    Statistical analysis validation for beating.

    Physical Meaning:
        Validates the statistical analysis results to ensure
        they meet quality criteria.
    """

    def __init__(self):
        """Initialize statistical validation."""
        self._quality_assessor = BeatingCoreValidationQuality()

    def validate_statistical_analysis(
        self, statistical_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate statistical analysis results.

        Physical Meaning:
            Validates the statistical analysis results to ensure
            they meet quality criteria.

        Args:
            statistical_results (Dict[str, Any]): Statistical analysis results.

        Returns:
            Dict[str, Any]: Statistical validation results.
        """
        # Check if statistical analysis is complete
        is_complete = statistical_results.get("analysis_complete", False)

        # Check significance testing quality
        significance_testing = statistical_results.get("significance_testing", {})
        significance_quality = self._quality_assessor.assess_significance_testing_quality(
            significance_testing
        )

        # Check pattern recognition quality
        pattern_recognition = statistical_results.get("pattern_recognition", {})
        pattern_quality = self._quality_assessor.assess_pattern_recognition_quality(pattern_recognition)

        # Check confidence analysis quality
        confidence_analysis = statistical_results.get("confidence_analysis", {})
        confidence_quality = self._quality_assessor.assess_confidence_analysis_quality(
            confidence_analysis
        )

        # Calculate overall quality
        overall_quality = np.mean(
            [significance_quality, pattern_quality, confidence_quality]
        )

        return {
            "is_complete": is_complete,
            "significance_quality": significance_quality,
            "pattern_quality": pattern_quality,
            "confidence_quality": confidence_quality,
            "overall_quality": overall_quality,
        }

