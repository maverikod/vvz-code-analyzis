"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law fitting methods for power law core analyzer.

This module provides power law fitting methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class PowerLawCoreFittingMixin:
    """Mixin providing power law fitting methods."""
    
    def _fit_power_law(self, region_data: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Fit power law to region data using full 7D BVP theory optimization.
        
        Physical Meaning:
            Fits a power law function to the region data using complete
            analytical methods based on 7D phase field theory principles.
            Implements full optimization with proper error handling and
            quality assessment.
            
        Mathematical Foundation:
            Uses scipy.optimize.curve_fit with proper bounds and constraints
            for accurate power law parameter estimation in 7D phase field theory.
            
        Args:
            region_data (Dict[str, np.ndarray]): Region data.
            
        Returns:
            Dict[str, float]: Power law fit parameters with full analysis.
        """
        try:
            from scipy.optimize import curve_fit
            
            amplitudes = region_data["amplitudes"]
            distances = region_data["distances"]
            
            # Avoid log of zero and ensure valid data
            valid_mask = (amplitudes > 0) & (distances > 0)
            if not np.any(valid_mask):
                return {
                    "exponent": 0.0,
                    "coefficient": 0.0,
                    "r_squared": 0.0,
                    "chi_squared": float("inf"),
                    "fitting_quality": 0.0,
                    "parameter_errors": [0.0, 0.0],
                }
            
            # Extract valid data
            valid_amplitudes = amplitudes[valid_mask]
            valid_distances = distances[valid_mask]
            
            if len(valid_distances) < 3:
                return {
                    "exponent": 0.0,
                    "coefficient": valid_amplitudes[0],
                    "r_squared": 0.0,
                    "chi_squared": float("inf"),
                    "fitting_quality": 0.0,
                    "parameter_errors": [0.0, 0.0],
                }
            
            # Define power law function for 7D BVP theory
            def power_law_func(r, amplitude, exponent):
                """Power law function for 7D phase field theory."""
                return amplitude * (r**exponent)
            
            # Initial parameter guesses based on 7D BVP theory
            initial_amplitude = np.mean(valid_amplitudes)
            initial_exponent = -2.0  # Typical 7D BVP exponent
            
            # Perform full curve fitting with proper bounds
            popt, pcov = curve_fit(
                power_law_func,
                valid_distances,
                valid_amplitudes,
                p0=[initial_amplitude, initial_exponent],
                maxfev=1000,
                bounds=([0.001, -10.0], [100.0, 0.0]),  # Reasonable bounds for 7D BVP
            )
            
            # Extract fitted parameters
            amplitude, exponent = popt
            
            # Compute comprehensive quality metrics
            r_squared = self._compute_r_squared_full(
                valid_distances, valid_amplitudes, popt, power_law_func
            )
            chi_squared = self._compute_chi_squared_full(
                valid_distances, valid_amplitudes, popt, power_law_func
            )
            reduced_chi_squared = chi_squared / (len(valid_distances) - 2)
            fitting_quality = self._compute_fitting_quality_full(pcov)
            
            # Compute parameter uncertainties
            parameter_errors = np.sqrt(np.diag(pcov))
            
            return {
                "exponent": float(exponent),
                "coefficient": float(amplitude),
                "r_squared": float(r_squared),
                "chi_squared": float(chi_squared),
                "reduced_chi_squared": float(reduced_chi_squared),
                "fitting_quality": float(fitting_quality),
                "parameter_errors": parameter_errors.tolist(),
                "covariance": pcov.tolist(),
            }
        
        except Exception as e:
            self.logger.error(f"Power law fitting failed: {e}")
            # Return default values with error indication
            return {
                "exponent": 0.0,
                "coefficient": 1.0,
                "r_squared": 0.0,
                "chi_squared": float("inf"),
                "fitting_quality": 0.0,
                "parameter_errors": [0.0, 0.0],
                "error": str(e),
            }

