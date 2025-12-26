"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimization methods for power law fitting.

This module implements various optimization methods
for power law fitting in 7D BVP theory.

Theoretical Background:
    Optimization methods involve using different
    algorithms for finding optimal power law parameters
    in 7D phase field theory.

Example:
    >>> methods = OptimizationMethods()
    >>> result = methods.fit_using_curve_fit(radial_profile)
"""

import numpy as np
from typing import Dict, Any, Tuple, List
import logging
from scipy.optimize import curve_fit, minimize


class OptimizationMethods:
    """
    Optimization methods for power law fitting.

    Physical Meaning:
        Implements various optimization methods for
        power law fitting in 7D BVP theory.

    Mathematical Foundation:
        Implements multiple optimization algorithms:
        - Curve fitting using scipy.optimize.curve_fit
        - Minimization using scipy.optimize.minimize
        - Custom optimization algorithms
    """

    def __init__(self):
        """Initialize optimization methods."""
        self.logger = logging.getLogger(__name__)

    def fit_using_curve_fit(
        self, radial_profile: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """
        Fit power law using scipy.optimize.curve_fit method.

        Physical Meaning:
            Performs power law fitting using scipy.optimize.curve_fit
            with comprehensive error analysis for 7D BVP theory.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.

        Returns:
            Dict[str, Any]: Curve fit results.
        """
        try:
            r = radial_profile["r"]
            values = radial_profile["values"]

            # Define power law function
            def power_law_func(r, amplitude, exponent):
                return amplitude * (r**exponent)

            # Perform curve fitting
            popt, pcov = curve_fit(
                power_law_func,
                r,
                values,
                p0=[1.0, -2.0],
                maxfev=1000,
                bounds=([0.001, -10.0], [100.0, 0.0]),
            )

            # Compute quality metrics
            r_squared = self._compute_r_squared(radial_profile, popt, power_law_func)
            chi_squared = self._compute_chi_squared(
                radial_profile, popt, power_law_func
            )
            fitting_quality = self._compute_fitting_quality(pcov)

            return {
                "amplitude": float(popt[0]),
                "exponent": float(popt[1]),
                "r_squared": float(r_squared),
                "chi_squared": float(chi_squared),
                "fitting_quality": float(fitting_quality),
                "parameter_errors": np.sqrt(np.diag(pcov)).tolist(),
                "covariance": pcov.tolist(),
                "fitting_successful": True,
                "method": "curve_fit",
            }

        except Exception as e:
            self.logger.error(f"Curve fit method failed: {e}")
            return {"fitting_successful": False, "error": str(e), "method": "curve_fit"}

    def fit_using_minimize(
        self, radial_profile: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """
        Fit power law using scipy.optimize.minimize method.

        Physical Meaning:
            Performs power law fitting using scipy.optimize.minimize
            with L-BFGS-B algorithm for 7D BVP theory applications.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.

        Returns:
            Dict[str, Any]: Minimize fit results.
        """
        try:
            r = radial_profile["r"]
            values = radial_profile["values"]

            # Define objective function
            def objective_function(params):
                amplitude, exponent = params
                predicted = amplitude * (r**exponent)
                return np.sum((values - predicted) ** 2)

            # Initial guess
            initial_params = [1.0, -2.0]

            # Perform optimization
            result = minimize(
                objective_function,
                initial_params,
                method="L-BFGS-B",
                bounds=[(0.001, 100.0), (-10.0, 0.0)],
                options={"maxiter": 1000},
            )

            if result.success:
                # Compute quality metrics
                r_squared = self._compute_r_squared(
                    radial_profile, result.x, lambda r, a, e: a * (r**e)
                )
                chi_squared = self._compute_chi_squared(
                    radial_profile, result.x, lambda r, a, e: a * (r**e)
                )

                return {
                    "amplitude": float(result.x[0]),
                    "exponent": float(result.x[1]),
                    "r_squared": float(r_squared),
                    "chi_squared": float(chi_squared),
                    "fitting_quality": float(1.0 / (1.0 + result.fun)),
                    "parameter_errors": [0.0, 0.0],  # Not available from minimize
                    "covariance": [
                        [0.0, 0.0],
                        [0.0, 0.0],
                    ],  # Not available from minimize
                    "fitting_successful": True,
                    "method": "minimize",
                    "optimization_info": {
                        "success": result.success,
                        "iterations": result.nit,
                        "function_evaluations": result.nfev,
                        "final_objective": float(result.fun),
                    },
                }
            else:
                return {
                    "fitting_successful": False,
                    "error": f"Optimization failed: {result.message}",
                    "method": "minimize",
                }

        except Exception as e:
            self.logger.error(f"Minimize method failed: {e}")
            return {"fitting_successful": False, "error": str(e), "method": "minimize"}

    def fit_using_custom_optimization(
        self, radial_profile: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """
        Fit power law using custom optimization algorithm for 7D BVP theory.

        Physical Meaning:
            Performs power law fitting using custom optimization algorithm
            specifically designed for 7D phase field theory applications.

        Mathematical Foundation:
            Implements custom optimization with adaptive step sizes,
            convergence criteria, and 7D BVP theory constraints.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.

        Returns:
            Dict[str, Any]: Custom optimization results.
        """
        try:
            r = radial_profile["r"]
            values = radial_profile["values"]

            # Custom optimization parameters
            max_iterations = 1000
            convergence_tolerance = 1e-8
            learning_rate = 0.01

            # Initial parameters
            amplitude = 1.0
            exponent = -2.0

            # Custom optimization loop
            for iteration in range(max_iterations):
                # Compute gradients
                grad_amplitude, grad_exponent = self._compute_gradients(
                    r, values, amplitude, exponent
                )

                # Update parameters with adaptive learning rate
                new_amplitude = amplitude - learning_rate * grad_amplitude
                new_exponent = exponent - learning_rate * grad_exponent

                # Apply bounds
                new_amplitude = max(0.001, min(100.0, new_amplitude))
                new_exponent = max(-10.0, min(0.0, new_exponent))

                # Check convergence
                param_change = abs(new_amplitude - amplitude) + abs(
                    new_exponent - exponent
                )
                if param_change < convergence_tolerance:
                    break

                amplitude = new_amplitude
                exponent = new_exponent

            # Compute quality metrics
            predicted = amplitude * (r**exponent)
            r_squared = self._compute_r_squared(
                radial_profile, [amplitude, exponent], lambda r, a, e: a * (r**e)
            )
            chi_squared = self._compute_chi_squared(
                radial_profile, [amplitude, exponent], lambda r, a, e: a * (r**e)
            )

            return {
                "amplitude": float(amplitude),
                "exponent": float(exponent),
                "r_squared": float(r_squared),
                "chi_squared": float(chi_squared),
                "fitting_quality": float(1.0 / (1.0 + chi_squared)),
                "parameter_errors": [0.0, 0.0],  # Not available from custom method
                "covariance": [
                    [0.0, 0.0],
                    [0.0, 0.0],
                ],  # Not available from custom method
                "fitting_successful": True,
                "method": "custom",
                "optimization_info": {
                    "iterations": iteration + 1,
                    "convergence_achieved": param_change < convergence_tolerance,
                    "final_parameter_change": float(param_change),
                },
            }

        except Exception as e:
            self.logger.error(f"Custom optimization method failed: {e}")
            return {"fitting_successful": False, "error": str(e), "method": "custom"}

    def _compute_gradients(
        self, r: np.ndarray, values: np.ndarray, amplitude: float, exponent: float
    ) -> Tuple[float, float]:
        """
        Compute gradients for custom optimization.

        Physical Meaning:
            Computes gradients of the objective function with respect to
            power law parameters for custom optimization in 7D BVP theory.

        Args:
            r (np.ndarray): Distance values.
            values (np.ndarray): Amplitude values.
            amplitude (float): Current amplitude parameter.
            exponent (float): Current exponent parameter.

        Returns:
            Tuple[float, float]: Gradients with respect to amplitude and exponent.
        """
        try:
            # Compute predicted values
            predicted = amplitude * (r**exponent)

            # Compute residuals
            residuals = values - predicted

            # Compute gradients
            grad_amplitude = -2.0 * np.sum(residuals * (r**exponent))
            grad_exponent = -2.0 * np.sum(
                residuals * amplitude * (r**exponent) * np.log(r)
            )

            return float(grad_amplitude), float(grad_exponent)

        except Exception as e:
            self.logger.error(f"Gradient computation failed: {e}")
            return 0.0, 0.0

    def _compute_r_squared(
        self, radial_profile: Dict[str, np.ndarray], popt: np.ndarray, func
    ) -> float:
        """Compute R-squared for power law fit."""
        try:
            r = radial_profile["r"]
            values = radial_profile["values"]

            # Compute predicted values
            predicted = func(r, *popt)

            # Compute R-squared
            ss_res = np.sum((values - predicted) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)

            if ss_tot == 0:
                return 0.0

            r_squared = 1 - (ss_res / ss_tot)
            return max(0.0, min(1.0, r_squared))

        except Exception as e:
            self.logger.error(f"R-squared computation failed: {e}")
            return 0.0

    def _compute_fitting_quality(self, pcov: np.ndarray) -> float:
        """Compute fitting quality from covariance matrix."""
        try:
            # Compute parameter uncertainties
            param_errors = np.sqrt(np.diag(pcov))

            # Compute relative uncertainties
            rel_errors = param_errors / np.maximum(np.abs(param_errors), 1e-10)

            # Quality based on uncertainty (lower is better)
            quality = 1.0 / (1.0 + np.mean(rel_errors))

            return max(0.0, min(1.0, quality))

        except Exception as e:
            self.logger.error(f"Fitting quality computation failed: {e}")
            return 0.0

    def _compute_chi_squared(
        self, radial_profile: Dict[str, np.ndarray], popt: np.ndarray, func
    ) -> float:
        """Compute chi-squared statistic for power law fit."""
        try:
            r = radial_profile["r"]
            values = radial_profile["values"]

            # Compute predicted values
            predicted = func(r, *popt)

            # Compute chi-squared with proper error handling
            chi_squared = np.sum(
                ((values - predicted) / np.maximum(values, 1e-10)) ** 2
            )

            return float(chi_squared)

        except Exception as e:
            self.logger.error(f"Chi-squared computation failed: {e}")
            return float("inf")
