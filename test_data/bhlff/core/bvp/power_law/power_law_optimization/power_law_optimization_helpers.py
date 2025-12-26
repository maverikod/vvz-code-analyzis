"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for power law optimization.

This module provides helper methods as a mixin class.
"""

import numpy as np
from typing import Dict


class PowerLawOptimizationHelpersMixin:
    """Mixin providing helper methods."""
    
    def _get_initial_parameters(self, region_data: Dict[str, np.ndarray]) -> np.ndarray:
        """Get initial parameter guess for optimization."""
        try:
            r = region_data["r"]
            values = region_data["values"]
            
            # Simple initial guess based on data
            if len(r) > 0 and len(values) > 0:
                # Estimate amplitude from maximum value
                amplitude = np.max(values)
                
                # Estimate exponent from slope
                if len(r) > 1:
                    log_r = np.log(r + 1e-10)
                    log_values = np.log(np.abs(values) + 1e-10)
                    slope = np.polyfit(log_r, log_values, 1)[0]
                    exponent = slope
                else:
                    exponent = -2.0
            else:
                amplitude = 1.0
                exponent = -2.0
            
            return np.array([amplitude, exponent])
            
        except Exception as e:
            self.logger.error(f"Initial parameter estimation failed: {e}")
            return np.array([1.0, -2.0])
    
    def _compute_fit_quality(
        self, region_data: Dict[str, np.ndarray], params: np.ndarray
    ) -> float:
        """Compute fit quality for given parameters."""
        try:
            r = region_data["r"]
            values = region_data["values"]
            
            if len(r) == 0 or len(values) == 0:
                return 0.0
            
            # Compute predicted values
            amplitude, exponent = params
            predicted = amplitude * (r**exponent)
            
            # Compute R-squared
            ss_res = np.sum((values - predicted) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            
            if ss_tot == 0:
                return 0.0
            
            r_squared = 1 - (ss_res / ss_tot)
            return max(0.0, min(1.0, r_squared))
            
        except Exception as e:
            self.logger.error(f"Fit quality computation failed: {e}")
            return 0.0
    
    def _compute_gradient(
        self, func, params: np.ndarray, h: float = 1e-6
    ) -> np.ndarray:
        """Compute numerical gradient of function."""
        try:
            gradient = np.zeros_like(params)
            
            for i in range(len(params)):
                # Forward difference
                params_plus = params.copy()
                params_plus[i] += h
                f_plus = func(params_plus)
                
                # Backward difference
                params_minus = params.copy()
                params_minus[i] -= h
                f_minus = func(params_minus)
                
                # Central difference
                gradient[i] = (f_plus - f_minus) / (2 * h)
            
            return gradient
            
        except Exception as e:
            self.logger.error(f"Gradient computation failed: {e}")
            return np.zeros_like(params)
    
    def _compute_parameter_sensitivity(
        self, param_value: float, param_name: str
    ) -> float:
        """Compute parameter sensitivity for adaptive adjustment."""
        try:
            # Simple sensitivity based on parameter magnitude
            if param_name == "amplitude":
                return min(1.0, abs(param_value) / 10.0)
            elif param_name == "exponent":
                return min(1.0, abs(param_value) / 5.0)
            else:
                return 0.1  # Default sensitivity
            
        except Exception as e:
            self.logger.error(f"Parameter sensitivity computation failed: {e}")
            return 0.1

