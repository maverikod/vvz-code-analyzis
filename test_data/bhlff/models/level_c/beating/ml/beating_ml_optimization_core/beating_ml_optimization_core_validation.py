"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation methods for beating ML optimization core.

This module provides validation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class BeatingMLOptimizationCoreValidationMixin:
    """Mixin providing validation methods."""
    
    def _validate_ml_optimization(
        self, optimization_results: Dict[str, Any], envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Validate ML optimization.
        
        Physical Meaning:
            Validates ML optimization results to ensure
            they meet quality and performance criteria.
        """
        self.logger.info("Validating ML optimization")
        
        # Extract optimization results
        optimized_parameters = optimization_results.get("optimized_parameters", {})
        best_performance = optimization_results.get("best_performance", 0.0)
        
        # Validate parameters
        parameter_validation = self._validate_parameters(optimized_parameters)
        
        # Validate performance
        performance_validation = self._validate_performance(best_performance)
        
        # Calculate overall validation
        overall_validation = self._calculate_overall_validation(
            parameter_validation, performance_validation
        )
        
        return {
            "parameter_validation": parameter_validation,
            "performance_validation": performance_validation,
            "overall_validation": overall_validation,
            "validation_complete": True,
        }
    
    def _validate_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters."""
        validation_results = {}
        
        for key, value in parameters.items():
            if key == "learning_rate":
                validation_results[key] = 0.001 <= value <= 0.1
            elif key == "batch_size":
                validation_results[key] = 16 <= value <= 128
            elif key == "epochs":
                validation_results[key] = 10 <= value <= 1000
            elif key == "dropout_rate":
                validation_results[key] = 0.0 <= value <= 0.5
            elif key == "regularization":
                validation_results[key] = 0.0 <= value <= 0.01
            else:
                validation_results[key] = True
        
        return validation_results
    
    def _validate_performance(self, performance: float) -> Dict[str, Any]:
        """Validate performance."""
        return {
            "performance_valid": performance > 0.5,
            "performance_score": performance,
            "quality_threshold": 0.5,
        }
    
    def _calculate_overall_validation(
        self,
        parameter_validation: Dict[str, Any],
        performance_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate overall validation."""
        # Calculate parameter validation score
        parameter_score = np.mean(list(parameter_validation.values()))
        
        # Calculate performance validation score
        performance_score = performance_validation.get("performance_score", 0.0)
        
        # Calculate overall validation
        overall_score = (parameter_score + performance_score) / 2.0
        is_valid = overall_score > 0.5
        
        return {
            "overall_score": overall_score,
            "is_valid": is_valid,
            "parameter_score": parameter_score,
            "performance_score": performance_score,
        }

