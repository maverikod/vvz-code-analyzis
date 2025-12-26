"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation methods for beating ML optimization classification.

This module provides validation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class BeatingMLOptimizationClassificationValidationMixin:
    """Mixin providing validation methods."""
    
    def _validate_classification_optimization(
        self, optimization_results: Dict[str, Any], envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Validate classification optimization.
        
        Physical Meaning:
            Validates classification optimization results to ensure
            they meet quality and performance criteria.
            
        Args:
            optimization_results (Dict[str, Any]): Optimization results.
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Classification validation results.
        """
        self.logger.info("Validating classification optimization")
        
        # Extract optimization results
        optimized_parameters = optimization_results.get("optimized_parameters", {})
        best_performance = optimization_results.get("best_performance", 0.0)
        
        # Validate classification parameters
        parameter_validation = self._validate_classification_parameters(
            optimized_parameters
        )
        
        # Validate classification performance
        performance_validation = self._validate_classification_performance(
            best_performance
        )
        
        # Calculate overall classification validation
        overall_validation = self._calculate_classification_overall_validation(
            parameter_validation, performance_validation
        )
        
        return {
            "parameter_validation": parameter_validation,
            "performance_validation": performance_validation,
            "overall_validation": overall_validation,
            "validation_complete": True,
        }
    
    def _validate_classification_parameters(
        self, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate classification parameters.
        
        Physical Meaning:
            Validates classification parameters to ensure they are
            within acceptable ranges.
            
        Args:
            parameters (Dict[str, Any]): Parameters to validate.
            
        Returns:
            Dict[str, Any]: Classification parameter validation results.
        """
        # Validate classification parameter ranges
        validation_results = {}
        
        for key, value in parameters.items():
            if key == "classification_threshold":
                validation_results[key] = 0.0 <= value <= 1.0
            elif key == "cross_validation_folds":
                validation_results[key] = 2 <= value <= 10
            elif key == "random_state":
                validation_results[key] = isinstance(value, int)
            else:
                validation_results[key] = True
        
        return validation_results
    
    def _validate_classification_performance(
        self, performance: float
    ) -> Dict[str, Any]:
        """
        Validate classification performance.
        
        Physical Meaning:
            Validates classification performance to ensure it meets
            quality criteria.
            
        Args:
            performance (float): Performance to validate.
            
        Returns:
            Dict[str, Any]: Classification performance validation results.
        """
        return {
            "performance_valid": performance > 0.6,
            "performance_score": performance,
            "quality_threshold": 0.6,
        }
    
    def _calculate_classification_overall_validation(
        self,
        parameter_validation: Dict[str, Any],
        performance_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate classification overall validation.
        
        Physical Meaning:
            Calculates overall classification validation score based on
            parameter and performance validation.
            
        Args:
            parameter_validation (Dict[str, Any]): Parameter validation results.
            performance_validation (Dict[str, Any]): Performance validation results.
            
        Returns:
            Dict[str, Any]: Classification overall validation results.
        """
        # Calculate parameter validation score
        parameter_score = np.mean(list(parameter_validation.values()))
        
        # Calculate performance validation score
        performance_score = performance_validation.get("performance_score", 0.0)
        
        # Calculate overall classification validation
        overall_score = (parameter_score + performance_score) / 2.0
        is_valid = overall_score > 0.6
        
        return {
            "overall_score": overall_score,
            "is_valid": is_valid,
            "parameter_score": parameter_score,
            "performance_score": performance_score,
        }

