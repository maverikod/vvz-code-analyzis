"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Parameter optimization for beating validation.

This module implements parameter optimization functionality
for beating validation.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationParameterOptimization:
    """
    Parameter optimization for beating validation.

    Physical Meaning:
        Provides parameter optimization functionality for
        beating validation.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize parameter optimization analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.optimization_tolerance = 1e-6
        self.max_iterations = 100

    def optimize_parameters(
        self, results: Dict[str, Any], initial_params: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Optimize validation parameters.

        Physical Meaning:
            Optimizes validation parameters to improve accuracy
            and efficiency.

        Args:
            results (Dict[str, Any]): Analysis results.
            initial_params (Dict[str, float]): Initial parameter values.

        Returns:
            Dict[str, float]: Optimized parameter values.
        """
        optimized_params = initial_params.copy()

        # Simple parameter optimization
        for iteration in range(self.max_iterations):
            # Calculate current performance
            current_performance = self._calculate_performance(results, optimized_params)

            # Adjust parameters
            optimized_params = self._adjust_parameters(
                optimized_params, current_performance
            )

            # Check convergence
            if self._check_convergence(optimized_params, initial_params):
                break

        return optimized_params

    def validate_optimization(
        self,
        results: Dict[str, Any],
        initial_params: Dict[str, float],
        optimized_params: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Validate parameter optimization.

        Physical Meaning:
            Validates that parameter optimization improves
            validation performance.

        Args:
            results (Dict[str, Any]): Analysis results.
            initial_params (Dict[str, float]): Initial parameters.
            optimized_params (Dict[str, float]): Optimized parameters.

        Returns:
            Dict[str, Any]: Validation results.
        """
        # Calculate performance with initial parameters
        initial_performance = self._calculate_performance(results, initial_params)

        # Calculate performance with optimized parameters
        optimized_performance = self._calculate_performance(results, optimized_params)

        # Calculate improvement
        improvement = optimized_performance - initial_performance
        improvement_percentage = (
            (improvement / initial_performance) * 100 if initial_performance > 0 else 0
        )

        return {
            "initial_performance": initial_performance,
            "optimized_performance": optimized_performance,
            "improvement": improvement,
            "improvement_percentage": improvement_percentage,
            "optimization_successful": improvement > 0,
        }

    def _calculate_performance(
        self, results: Dict[str, Any], params: Dict[str, float]
    ) -> float:
        """Calculate performance metric for given parameters."""
        # Simplified performance calculation
        tolerance = params.get("optimization_tolerance", 1e-6)
        significance = params.get("statistical_significance", 0.05)

        # Performance based on parameter values
        performance = (1.0 / tolerance) * significance
        return min(1.0, performance / 1000.0)

    def _adjust_parameters(
        self, params: Dict[str, float], performance: float
    ) -> Dict[str, float]:
        """Adjust parameters based on performance."""
        adjusted_params = params.copy()
        adjustment_factor = 0.01

        # Adjust tolerance
        if performance < 0.5:
            adjusted_params["optimization_tolerance"] *= 1 - adjustment_factor
        else:
            adjusted_params["optimization_tolerance"] *= 1 + adjustment_factor

        # Adjust statistical significance
        if performance < 0.6:
            adjusted_params["statistical_significance"] *= 1 + adjustment_factor
        else:
            adjusted_params["statistical_significance"] *= 1 - adjustment_factor

        # Ensure parameters stay within valid ranges
        adjusted_params["optimization_tolerance"] = max(
            1e-12, min(1e-4, adjusted_params["optimization_tolerance"])
        )
        adjusted_params["statistical_significance"] = max(
            0.01, min(0.1, adjusted_params["statistical_significance"])
        )

        return adjusted_params

    def _check_convergence(
        self, current_params: Dict[str, float], initial_params: Dict[str, float]
    ) -> bool:
        """Check if optimization has converged."""
        for key in current_params:
            if key in initial_params:
                relative_change = (
                    abs(current_params[key] - initial_params[key]) / initial_params[key]
                )
                if relative_change > self.optimization_tolerance:
                    return False
        return True
