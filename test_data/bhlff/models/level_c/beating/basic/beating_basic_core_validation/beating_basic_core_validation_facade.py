"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for beating core validation.
"""

import numpy as np
from typing import Dict, Any

from .beating_basic_core_validation_base import BeatingCoreValidationBase
from .beating_basic_core_validation_core import BeatingCoreValidationCore
from .beating_basic_core_validation_statistical import BeatingCoreValidationStatistical
from .beating_basic_core_validation_optimization import BeatingCoreValidationOptimization


class BeatingCoreValidation(BeatingCoreValidationBase):
    """
    Core beating validation for Level C.

    Physical Meaning:
        Validates analysis results to ensure they meet quality and consistency
        criteria for reliable beating analysis.

    Mathematical Foundation:
        Validates analysis results through quality assessment and
        consistency checking to ensure reliability.
    """

    def __init__(self):
        """Initialize core beating validation."""
        super().__init__()
        self._core_validator = BeatingCoreValidationCore()
        self._statistical_validator = BeatingCoreValidationStatistical()
        self._optimization_validator = BeatingCoreValidationOptimization()

    def validate_analysis_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate analysis results.

        Physical Meaning:
            Validates the analysis results to ensure
            they meet quality and consistency criteria.

        Mathematical Foundation:
            Validates analysis results through quality assessment and
            consistency checking to ensure reliability.

        Args:
            results (Dict[str, Any]): Analysis results to validate.

        Returns:
            Dict[str, Any]: Validation results.
        """
        self.logger.info("Starting analysis results validation")

        # Validate core analysis
        core_validation = self._core_validator.validate_core_analysis(
            results.get("core_analysis", {})
        )

        # Validate statistical analysis
        statistical_validation = self._statistical_validator.validate_statistical_analysis(
            results.get("statistical_analysis", {})
        )

        # Validate optimization results
        optimization_validation = self._optimization_validator.validate_optimization_results(
            results.get("optimization_results", {})
        )

        # Calculate overall validation
        overall_validation = self._calculate_overall_validation(
            core_validation, statistical_validation, optimization_validation
        )

        validation_results = {
            "core_validation": core_validation,
            "statistical_validation": statistical_validation,
            "optimization_validation": optimization_validation,
            "overall_validation": overall_validation,
            "validation_complete": True,
        }

        self.logger.info("Analysis results validation completed")
        return validation_results

    def _calculate_overall_validation(
        self,
        core_validation: Dict[str, Any],
        statistical_validation: Dict[str, Any],
        optimization_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate overall validation.

        Physical Meaning:
            Calculates the overall validation score based on
            individual validation results.

        Args:
            core_validation (Dict[str, Any]): Core validation results.
            statistical_validation (Dict[str, Any]): Statistical validation results.
            optimization_validation (Dict[str, Any]): Optimization validation results.

        Returns:
            Dict[str, Any]: Overall validation results.
        """
        # Calculate overall quality
        core_quality = core_validation.get("overall_quality", 0.0)
        statistical_quality = statistical_validation.get("overall_quality", 0.0)
        optimization_quality = optimization_validation.get("overall_quality", 0.0)

        overall_quality = np.mean(
            [core_quality, statistical_quality, optimization_quality]
        )

        # Determine validation status
        is_valid = overall_quality > 0.5

        return {
            "overall_quality": overall_quality,
            "is_valid": is_valid,
            "core_quality": core_quality,
            "statistical_quality": statistical_quality,
            "optimization_quality": optimization_quality,
        }

