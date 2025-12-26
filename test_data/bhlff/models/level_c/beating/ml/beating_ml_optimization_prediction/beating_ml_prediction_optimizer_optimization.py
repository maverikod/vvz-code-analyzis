"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimization methods for beating ML prediction optimization.

This module provides optimization methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class BeatingMLPredictionOptimizerOptimizationMixin:
    """Mixin providing optimization methods."""
    
    def _optimize_prediction_parameters(
        self, envelope: np.ndarray, max_iterations: int = 75, tolerance: float = 1e-6
    ) -> Dict[str, Any]:
        """
        Optimize prediction parameters.
        
        Physical Meaning:
            Performs iterative optimization of prediction parameters
            to improve beating prediction performance.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            max_iterations (int): Maximum optimization iterations.
            tolerance (float): Convergence tolerance.
            
        Returns:
            Dict[str, Any]: Prediction optimization results.
        """
        self.logger.info("Optimizing prediction parameters")
        
        # Initialize prediction parameters
        current_parameters = self._initialize_prediction_parameters()
        best_parameters = current_parameters.copy()
        best_performance = 0.0
        
        # Optimization loop
        for iteration in range(max_iterations):
            # Calculate current prediction performance
            current_performance = self._calculate_prediction_performance(
                {"parameters": current_parameters}, envelope
            ).get("prediction_accuracy", 0.0)
            
            # Update best parameters if performance improved
            if current_performance > best_performance:
                best_performance = current_performance
                best_parameters = current_parameters.copy()
            
            # Adjust prediction parameters
            current_parameters = self._adjust_prediction_parameters(
                current_parameters, current_performance
            )
            
            # Check convergence
            if self._check_prediction_convergence(
                current_performance, best_performance, tolerance
            ):
                break
        
        return {
            "optimized_parameters": best_parameters,
            "best_performance": best_performance,
            "iterations": iteration + 1,
            "converged": iteration < max_iterations - 1,
        }
    
    def _adjust_prediction_parameters(
        self, parameters: Dict[str, Any], performance: float
    ) -> Dict[str, Any]:
        """
        Adjust prediction parameters.
        
        Physical Meaning:
            Adjusts prediction parameters based on current performance
            to improve optimization.
            
        Args:
            parameters (Dict[str, Any]): Current parameters.
            performance (float): Current performance.
            
        Returns:
            Dict[str, Any]: Adjusted prediction parameters.
        """
        # Full prediction parameter adjustment using 7D BVP theory
        adjusted_parameters = parameters.copy()
        
        # Use vectorized 7D phase field optimization for parameter adjustment
        if self.vectorized_processor is not None:
            # Use vectorized optimization for better performance
            phase_field_optimization = self._optimize_with_vectorized_processing(
                np.array([performance]), parameters
            )
        else:
            # Fallback to non-vectorized optimization
            phase_field_optimization = self._compute_7d_phase_field_optimization(
                performance, parameters
            )
        
        # Adjust prediction horizon based on 7D phase field analysis
        if "prediction_horizon" in adjusted_parameters:
            horizon = adjusted_parameters["prediction_horizon"]
            phase_coherence = phase_field_optimization.get("phase_coherence", 0.5)
            topological_charge = phase_field_optimization.get("topological_charge", 0.0)
            
            # Adjust based on 7D phase field properties
            if phase_coherence < 0.6 or abs(topological_charge) > 0.5:
                # Increase horizon for complex phase field configurations
                adjusted_parameters["prediction_horizon"] = min(horizon + 2, 25)
            elif phase_coherence > 0.8 and abs(topological_charge) < 0.2:
                # Decrease horizon for simple phase field configurations
                adjusted_parameters["prediction_horizon"] = max(horizon - 1, 3)
        
        # Adjust regularization strength based on 7D phase field complexity
        if "regularization_strength" in adjusted_parameters:
            energy_density = phase_field_optimization.get("energy_density", 1.0)
            adjusted_parameters["regularization_strength"] = min(
                0.1, energy_density * 0.01
            )
        
        return adjusted_parameters
    
    def _check_prediction_convergence(
        self, current_performance: float, best_performance: float, tolerance: float
    ) -> bool:
        """
        Check prediction convergence.
        
        Physical Meaning:
            Checks if prediction optimization has converged based on
            performance improvement and tolerance.
            
        Args:
            current_performance (float): Current performance.
            best_performance (float): Best performance.
            tolerance (float): Convergence tolerance.
            
        Returns:
            bool: True if converged.
        """
        # Check if performance improvement is below tolerance
        performance_improvement = abs(current_performance - best_performance)
        return performance_improvement < tolerance

