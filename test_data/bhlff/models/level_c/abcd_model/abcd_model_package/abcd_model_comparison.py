"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Comparison methods for ABCD model.

This module provides comparison methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class ABCDModelComparisonMixin:
    """Mixin providing comparison methods."""
    
    def compare_with_numerical(
        self, numerical_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare with numerical simulation results.
        
        Physical Meaning:
            Compares ABCD model predictions with numerical simulation
            results, computing errors and validating the model accuracy.
            
        Mathematical Foundation:
            Computes various error metrics:
            - Frequency errors: |ω_ABCD - ω_num| / ω_num
            - Quality factor errors: |Q_ABCD - Q_num| / Q_num
            - Admittance errors: |Y_ABCD - Y_num| / |Y_num|
            
        Args:
            numerical_results (Dict[str, Any]): Numerical simulation results.
            
        Returns:
            Dict[str, Any]: Comparison results with error metrics.
        """
        # Extract numerical data
        numerical_frequencies = numerical_results.get("frequencies", [])
        numerical_admittance = numerical_results.get("admittance", [])
        numerical_modes = numerical_results.get("modes", [])
        
        # Compute ABCD predictions
        frequency_range = (min(numerical_frequencies), max(numerical_frequencies))
        abcd_modes = self.find_system_modes(frequency_range)
        
        # Compare frequencies
        frequency_errors = []
        for abcd_mode in abcd_modes:
            # Find closest numerical mode
            closest_numerical = min(
                numerical_modes,
                key=lambda m: abs(m.get("frequency", 0) - abcd_mode.frequency),
            )
            
            if "frequency" in closest_numerical:
                error = (
                    abs(abcd_mode.frequency - closest_numerical["frequency"])
                    / closest_numerical["frequency"]
                )
                frequency_errors.append(error)
        
        # Compare quality factors
        quality_errors = []
        for abcd_mode in abcd_modes:
            closest_numerical = min(
                numerical_modes,
                key=lambda m: abs(m.get("frequency", 0) - abcd_mode.frequency),
            )
            
            if "quality_factor" in closest_numerical:
                error = (
                    abs(abcd_mode.quality_factor - closest_numerical["quality_factor"])
                    / closest_numerical["quality_factor"]
                )
                quality_errors.append(error)
        
        # Compare admittance
        admittance_errors = []
        for freq in numerical_frequencies:
            abcd_admittance = self.compute_system_admittance(freq)
            numerical_admittance_val = numerical_admittance[
                numerical_frequencies.index(freq)
            ]
            
            if abs(numerical_admittance_val) > 1e-12:
                error = abs(abcd_admittance - numerical_admittance_val) / abs(
                    numerical_admittance_val
                )
                admittance_errors.append(error)
        
        return {
            "frequency_errors": frequency_errors,
            "quality_errors": quality_errors,
            "admittance_errors": admittance_errors,
            "max_frequency_error": max(frequency_errors) if frequency_errors else 0.0,
            "max_quality_error": max(quality_errors) if quality_errors else 0.0,
            "max_admittance_error": (
                max(admittance_errors) if admittance_errors else 0.0
            ),
            "abcd_modes": abcd_modes,
            "numerical_modes": numerical_modes,
            "comparison_passed": (
                (max(frequency_errors) if frequency_errors else 0.0) < 0.05
                and (max(quality_errors) if quality_errors else 0.0) < 0.10
            ),
        }

