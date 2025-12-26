"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quality computation methods for power law optimization.

This module provides quality computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class PowerLawOptimizationQualityMixin:
    """Mixin providing quality computation methods."""
    
    def _calculate_optimization_quality(
        self, optimized_results: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate comprehensive quality of optimization results using full 7D BVP theory.
        
        Physical Meaning:
            Computes comprehensive quality metrics for optimization results
            based on 7D phase field theory principles and statistical analysis.
            Implements full quality assessment with multiple indicators.
            
        Mathematical Foundation:
            Uses multiple quality indicators including success rate,
            improvement statistics, convergence metrics, and parameter
            uncertainty analysis for robust quality assessment.
        """
        try:
            if not optimized_results:
                return {
                    "average_improvement": 0.0,
                    "optimization_success_rate": 0.0,
                    "overall_quality": 0.0,
                    "total_improvement": 0.0,
                    "convergence_rate": 0.0,
                    "parameter_uncertainty": 0.0,
                    "physical_constraints_quality": 0.0,
                }
            
            # Extract quality metrics
            successful_results = [
                r for r in optimized_results if r.get("optimization_successful", False)
            ]
            total_results = len(optimized_results)
            
            # Compute success rate
            success_rate = (
                len(successful_results) / total_results if total_results > 0 else 0.0
            )
            
            # Compute improvement statistics
            improvements = [r.get("improvement", 0.0) for r in successful_results]
            average_improvement = np.mean(improvements) if improvements else 0.0
            total_improvement = np.sum(improvements) if improvements else 0.0
            
            # Compute convergence rate
            convergence_results = [
                r for r in successful_results if r.get("convergence_achieved", False)
            ]
            convergence_rate = (
                len(convergence_results) / total_results if total_results > 0 else 0.0
            )
            
            # Compute parameter uncertainty quality
            parameter_uncertainty = self._compute_parameter_uncertainty_quality(
                successful_results
            )
            
            # Compute physical constraints quality
            physical_constraints_quality = self._compute_physical_constraints_quality(
                successful_results
            )
            
            # Compute overall quality using weighted combination
            quality_factors = [
                success_rate,
                min(1.0, average_improvement / 10.0),  # Normalize improvement
                convergence_rate,
                parameter_uncertainty,
                physical_constraints_quality,
            ]
            
            overall_quality = np.mean(quality_factors)
            
            return {
                "average_improvement": float(average_improvement),
                "optimization_success_rate": float(success_rate),
                "overall_quality": float(overall_quality),
                "total_improvement": float(total_improvement),
                "convergence_rate": float(convergence_rate),
                "parameter_uncertainty": float(parameter_uncertainty),
                "physical_constraints_quality": float(physical_constraints_quality),
                "quality_factors": {
                    "success_rate": float(success_rate),
                    "improvement_quality": float(min(1.0, average_improvement / 10.0)),
                    "convergence_quality": float(convergence_rate),
                    "uncertainty_quality": float(parameter_uncertainty),
                    "physical_quality": float(physical_constraints_quality),
                },
            }
            
        except Exception as e:
            self.logger.error(f"Optimization quality calculation failed: {e}")
            return {
                "average_improvement": 0.0,
                "optimization_success_rate": 0.0,
                "overall_quality": 0.0,
                "total_improvement": 0.0,
                "convergence_rate": 0.0,
                "parameter_uncertainty": 0.0,
                "physical_constraints_quality": 0.0,
                "error": str(e),
            }
    
    def _compute_parameter_uncertainty_quality(
        self, successful_results: List[Dict[str, Any]]
    ) -> float:
        """
        Compute parameter uncertainty quality for optimization results.
        
        Physical Meaning:
            Evaluates parameter uncertainty quality based on
            parameter errors and covariance analysis for 7D BVP theory.
            
        Args:
            successful_results (List[Dict[str, Any]]): Successful optimization results.
            
        Returns:
            float: Parameter uncertainty quality (0-1).
        """
        try:
            if not successful_results:
                return 0.0
            
            uncertainty_qualities = []
            
            for result in successful_results:
                parameter_errors = result.get("parameter_errors", [0.0, 0.0])
                amplitude = result.get("optimized_amplitude", result.get("amplitude", 1.0))
                exponent = result.get("optimized_exponent", result.get("exponent", -2.0))
                
                if len(parameter_errors) >= 2:
                    amplitude_error = parameter_errors[0]
                    exponent_error = parameter_errors[1]
                    
                    # Relative errors
                    rel_amplitude_error = amplitude_error / max(abs(amplitude), 1e-10)
                    rel_exponent_error = exponent_error / max(abs(exponent), 1e-10)
                    
                    # Uncertainty quality (lower relative error is better)
                    uncertainty_quality = max(
                        0.0,
                        min(
                            1.0, 1.0 / (1.0 + rel_amplitude_error + rel_exponent_error)
                        ),
                    )
                    uncertainty_qualities.append(uncertainty_quality)
            
            return np.mean(uncertainty_qualities) if uncertainty_qualities else 0.0
            
        except Exception as e:
            self.logger.error(f"Parameter uncertainty quality computation failed: {e}")
            return 0.0
    
    def _compute_physical_constraints_quality(
        self, successful_results: List[Dict[str, Any]]
    ) -> float:
        """
        Compute physical constraints quality for optimization results.
        
        Physical Meaning:
            Evaluates physical constraints quality based on
            parameter bounds and 7D BVP theory principles.
            
        Args:
            successful_results (List[Dict[str, Any]]): Successful optimization results.
            
        Returns:
            float: Physical constraints quality (0-1).
        """
        try:
            if not successful_results:
                return 0.0
            
            physical_qualities = []
            
            for result in successful_results:
                amplitude = result.get("optimized_amplitude", result.get("amplitude", 1.0))
                exponent = result.get("optimized_exponent", result.get("exponent", -2.0))
                
                quality = 1.0
                
                # Check amplitude bounds for 7D BVP theory
                if amplitude <= 0:
                    quality *= 0.0
                elif amplitude > 100:
                    quality *= 0.7
                
                # Check exponent bounds for 7D BVP theory
                if abs(exponent) > 10:
                    quality *= 0.5
                elif abs(exponent) > 5:
                    quality *= 0.8
                
                physical_qualities.append(quality)
            
            return np.mean(physical_qualities) if physical_qualities else 0.0
            
        except Exception as e:
            self.logger.error(f"Physical constraints quality computation failed: {e}")
            return 0.0

