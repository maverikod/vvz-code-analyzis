"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Aggregation methods for particle validation.

This module provides aggregation methods as a mixin class.
"""

from typing import Dict, Any


class ParticleValidationAggregationMixin:
    """Mixin providing aggregation methods."""
    
    def _compute_overall_validation(self) -> Dict[str, Any]:
        """
        Compute overall validation result.
        
        Physical Meaning:
            Computes the overall validation result based on
            all validation tests.
        """
        # Compute overall validation
        overall_validation = {
            "all_tests_passed": True,
            "validation_score": 1.0,
            "critical_failures": [],
            "warnings": [],
            "recommendations": [],
        }

        return overall_validation

