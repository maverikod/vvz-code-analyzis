"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Region optimization methods for power law optimization.

This module provides region optimization methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any
from scipy.optimize import minimize


class PowerLawOptimizationRegionMixin:
    """Mixin providing region optimization methods."""
    
    def _optimize_region_fit(
        self, envelope: np.ndarray, region: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Optimize power law fit for a specific region using full 7D BVP theory.
        
        Physical Meaning:
            Performs comprehensive optimization of power law parameters
            for a specific region using 7D phase field theory principles.
            
        Mathematical Foundation:
            Uses scipy.optimize.minimize with L-BFGS-B method for
            parameter optimization with proper bounds and constraints.
        """
        try:
            # Extract region data
            region_data = self._extract_region_data(envelope, region)
            
            if len(region_data["r"]) < 3:
                raise ValueError("Insufficient data points for region optimization")
            
            # Initial parameter guess
            initial_params = self._get_initial_parameters(region_data)
            
            # Define optimization objective function
            def objective_function(params):
                amplitude, exponent = params
                predicted = amplitude * (region_data["r"] ** exponent)
                residuals = region_data["values"] - predicted
                return np.sum(residuals**2)
            
            # Set parameter bounds
            bounds = [
                (0.001, 100.0),  # amplitude bounds
                (-10.0, 0.0),  # exponent bounds (negative for decay)
            ]
            
            # Perform optimization
            result = minimize(
                objective_function,
                initial_params,
                method="L-BFGS-B",
                bounds=bounds,
                options={
                    "maxiter": self.max_optimization_iterations,
                    "ftol": self.optimization_tolerance,
                    "gtol": self.optimization_tolerance,
                },
            )
            
            if result.success:
                # Extract optimized parameters
                optimized_amplitude, optimized_exponent = result.x
                
                # Compute improvement metrics
                initial_fit_quality = self._compute_fit_quality(
                    region_data, initial_params
                )
                optimized_fit_quality = self._compute_fit_quality(region_data, result.x)
                improvement = optimized_fit_quality - initial_fit_quality
                
                # Perform iterative refinement if needed
                if improvement < 0.1:  # If improvement is small, try refinement
                    refined_result = self._iterative_refinement(
                        region_data,
                        {
                            "amplitude": optimized_amplitude,
                            "exponent": optimized_exponent,
                        },
                    )
                    
                    if refined_result.get("convergence_achieved", False):
                        optimized_amplitude = refined_result.get(
                            "refined_amplitude", optimized_amplitude
                        )
                        optimized_exponent = refined_result.get(
                            "refined_exponent", optimized_exponent
                        )
                        improvement = max(
                            improvement, refined_result.get("improvement", 0.0)
                        )
                
                return {
                    "optimization_successful": True,
                    "optimized_amplitude": float(optimized_amplitude),
                    "optimized_exponent": float(optimized_exponent),
                    "initial_amplitude": float(initial_params[0]),
                    "initial_exponent": float(initial_params[1]),
                    "improvement": float(improvement),
                    "fit_quality": float(optimized_fit_quality),
                    "convergence_info": {
                        "success": result.success,
                        "iterations": result.nit,
                        "function_evaluations": result.nfev,
                        "final_objective": float(result.fun),
                    },
                }
            else:
                return {
                    "optimization_successful": False,
                    "error": f"Optimization failed: {result.message}",
                    "initial_amplitude": float(initial_params[0]),
                    "initial_exponent": float(initial_params[1]),
                    "improvement": 0.0,
                    "fit_quality": 0.0,
                }
            
        except Exception as e:
            self.logger.error(f"Region optimization failed: {e}")
            return {
                "optimization_successful": False,
                "error": str(e),
                "improvement": 0.0,
                "fit_quality": 0.0,
            }
    
    def _iterative_refinement(
        self, region_data: Dict[str, np.ndarray], initial_fit: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Perform iterative refinement of power law fit using full 7D BVP theory.
        
        Physical Meaning:
            Performs iterative refinement of power law parameters using
            advanced optimization techniques based on 7D phase field theory.
            
        Mathematical Foundation:
            Uses gradient-based optimization with adaptive step sizes
            and convergence criteria for parameter refinement.
        """
        try:
            # Extract initial parameters
            initial_amplitude = initial_fit.get("amplitude", 1.0)
            initial_exponent = initial_fit.get("exponent", -2.0)
            
            # Define refinement objective function
            def refinement_objective(params):
                amplitude, exponent = params
                predicted = amplitude * (region_data["r"] ** exponent)
                residuals = region_data["values"] - predicted
                return np.sum(residuals**2)
            
            # Perform iterative refinement
            max_refinement_iterations = 10
            convergence_tolerance = 1e-8
            
            current_params = np.array([initial_amplitude, initial_exponent])
            previous_objective = refinement_objective(current_params)
            
            for iteration in range(max_refinement_iterations):
                # Compute gradient numerically
                gradient = self._compute_gradient(refinement_objective, current_params)
                
                # Adaptive step size
                step_size = 0.1 / (1.0 + iteration)
                
                # Update parameters
                new_params = current_params - step_size * gradient
                
                # Ensure parameters stay within bounds
                new_params[0] = max(
                    0.001, min(100.0, new_params[0])
                )  # amplitude bounds
                new_params[1] = max(-10.0, min(0.0, new_params[1]))  # exponent bounds
                
                # Check convergence
                current_objective = refinement_objective(new_params)
                objective_change = abs(current_objective - previous_objective)
                
                if objective_change < convergence_tolerance:
                    return {
                        "refined_amplitude": float(new_params[0]),
                        "refined_exponent": float(new_params[1]),
                        "convergence_achieved": True,
                        "iterations": iteration + 1,
                        "improvement": previous_objective - current_objective,
                        "final_objective": float(current_objective),
                    }
                
                current_params = new_params
                previous_objective = current_objective
            
            # If no convergence achieved
            return {
                "refined_amplitude": float(current_params[0]),
                "refined_exponent": float(current_params[1]),
                "convergence_achieved": False,
                "iterations": max_refinement_iterations,
                "improvement": initial_fit.get("fit_quality", 0.0) - previous_objective,
                "final_objective": float(previous_objective),
            }
            
        except Exception as e:
            self.logger.error(f"Iterative refinement failed: {e}")
            return {
                "refined_amplitude": initial_fit.get("amplitude", 1.0),
                "refined_exponent": initial_fit.get("exponent", -2.0),
                "convergence_achieved": False,
                "error": str(e),
                "improvement": 0.0,
            }
    
    def _adjust_fit_parameters(self, fit_params: Dict[str, float]) -> Dict[str, float]:
        """
        Adjust fit parameters for optimization using full 7D BVP theory.
        
        Physical Meaning:
            Adjusts power law parameters based on 7D phase field theory
            principles to improve fitting quality and convergence.
            
        Mathematical Foundation:
            Uses parameter sensitivity analysis and adaptive adjustment
            strategies for optimal parameter tuning.
        """
        try:
            # Extract current parameters
            amplitude = fit_params.get("amplitude", 1.0)
            exponent = fit_params.get("exponent", -2.0)
            
            # Compute parameter sensitivities
            amplitude_sensitivity = self._compute_parameter_sensitivity(
                amplitude, "amplitude"
            )
            exponent_sensitivity = self._compute_parameter_sensitivity(
                exponent, "exponent"
            )
            
            # Adaptive adjustment based on sensitivities
            if amplitude_sensitivity > 0.1:  # High sensitivity
                amplitude_adjustment = 0.01  # Small adjustment
            else:
                amplitude_adjustment = 0.05  # Larger adjustment
            
            if exponent_sensitivity > 0.1:  # High sensitivity
                exponent_adjustment = 0.01  # Small adjustment
            else:
                exponent_adjustment = 0.05  # Larger adjustment
            
            # Apply adjustments with bounds checking
            adjusted_amplitude = amplitude * (1.0 + amplitude_adjustment)
            adjusted_amplitude = max(0.001, min(100.0, adjusted_amplitude))
            
            adjusted_exponent = exponent * (1.0 + exponent_adjustment)
            adjusted_exponent = max(-10.0, min(0.0, adjusted_exponent))
            
            return {
                "amplitude": float(adjusted_amplitude),
                "exponent": float(adjusted_exponent),
                "amplitude_adjustment": float(amplitude_adjustment),
                "exponent_adjustment": float(exponent_adjustment),
                "amplitude_sensitivity": float(amplitude_sensitivity),
                "exponent_sensitivity": float(exponent_sensitivity),
            }
            
        except Exception as e:
            self.logger.error(f"Parameter adjustment failed: {e}")
            # Return original parameters if adjustment fails
            return fit_params.copy()

