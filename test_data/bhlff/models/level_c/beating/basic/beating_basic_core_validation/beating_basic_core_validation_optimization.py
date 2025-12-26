"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimization results validation for beating.
"""

import numpy as np
from typing import Dict, Any

from .beating_basic_core_validation_quality import BeatingCoreValidationQuality


class BeatingCoreValidationOptimization:
    """
    Optimization results validation for beating.

    Physical Meaning:
        Validates the optimization results to ensure
        they meet quality criteria.
    """

    def __init__(self):
        """Initialize optimization validation."""
        self._quality_assessor = BeatingCoreValidationQuality()

    def validate_optimization_results(
        self, optimization_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate optimization results.

        Physical Meaning:
            Validates the optimization results to ensure
            they meet quality criteria.

        Args:
            optimization_results (Dict[str, Any]): Optimization results.

        Returns:
            Dict[str, Any]: Optimization validation results.
        """
        # Check if optimization is complete
        is_complete = optimization_results.get("optimization_complete", False)

        # Check parameter optimization quality
        parameter_optimization = optimization_results.get("parameter_optimization", {})
        parameter_quality = self._quality_assessor.assess_parameter_optimization_quality(
            parameter_optimization
        )

        # Check threshold optimization quality
        threshold_optimization = optimization_results.get("threshold_optimization", {})
        threshold_quality = self._quality_assessor.assess_threshold_optimization_quality(
            threshold_optimization
        )

        # Check method optimization quality
        method_optimization = optimization_results.get("method_optimization", {})
        method_quality = self._quality_assessor.assess_method_optimization_quality(method_optimization)

        # Calculate overall quality
        overall_quality = np.mean(
            [parameter_quality, threshold_quality, method_quality]
        )

        return {
            "is_complete": is_complete,
            "parameter_quality": parameter_quality,
            "threshold_quality": threshold_quality,
            "method_quality": method_quality,
            "overall_quality": overall_quality,
        }

