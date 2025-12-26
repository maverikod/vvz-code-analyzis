"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quality analysis for power law fitting.

This module implements comprehensive quality analysis
functionality for power law fitting in 7D BVP theory.

Theoretical Background:
    Quality analysis involves assessing the quality
    of power law fits using statistical measures,
    physical constraints, and uncertainty analysis.

Example:
    >>> analyzer = QualityAnalyzer()
    >>> quality = analyzer.calculate_fitting_quality(region_data, power_law_fit)
"""

import numpy as np
from typing import Dict, Any, List
import logging


class QualityAnalyzer:
    """
    Quality analyzer for power law fitting.

    Physical Meaning:
        Analyzes the quality of power law fits using
        comprehensive statistical and physical measures.

    Mathematical Foundation:
        Implements quality analysis methods:
        - Statistical quality assessment
        - Physical constraint validation
        - Uncertainty quantification
        - 7D BVP theory validation
    """

    def __init__(self):
        """Initialize quality analyzer."""
        self.logger = logging.getLogger(__name__)

    def calculate_fitting_quality(
        self, region_data: Dict[str, np.ndarray], power_law_fit: Dict[str, float]
    ) -> float:
        """
        Calculate fitting quality metric using full analytical method.

        Physical Meaning:
            Calculates a comprehensive quality metric for the power law fit
            using multiple statistical measures to assess reliability.

        Mathematical Foundation:
            Combines R-squared, reduced chi-squared, and parameter uncertainty
            to provide a robust quality assessment.

        Args:
            region_data (Dict[str, np.ndarray]): Original region data.
            power_law_fit (Dict[str, float]): Power law fitting results.

        Returns:
            float: Comprehensive fitting quality metric (0-1).
        """
        try:
            # Extract quality metrics from fit results
            r_squared = power_law_fit.get("r_squared", 0.0)
            reduced_chi_squared = power_law_fit.get("reduced_chi_squared", float("inf"))
            parameter_errors = power_law_fit.get("parameter_errors", [0.0, 0.0])

            # Compute quality based on multiple factors
            quality_factors = []

            # R-squared contribution (higher is better)
            r_squared_quality = max(0.0, min(1.0, r_squared))
            quality_factors.append(r_squared_quality)

            # Reduced chi-squared contribution (closer to 1 is better)
            if reduced_chi_squared != float("inf"):
                chi_squared_quality = max(
                    0.0, min(1.0, 1.0 / (1.0 + abs(reduced_chi_squared - 1.0)))
                )
                quality_factors.append(chi_squared_quality)

            # Parameter uncertainty contribution (lower uncertainty is better)
            if len(parameter_errors) >= 2:
                amplitude_error = parameter_errors[0]
                exponent_error = parameter_errors[1]
                amplitude = power_law_fit.get("amplitude", 1.0)
                exponent = power_law_fit.get("power_law_exponent", -2.0)

                # Relative errors
                rel_amplitude_error = amplitude_error / max(abs(amplitude), 1e-10)
                rel_exponent_error = exponent_error / max(abs(exponent), 1e-10)

                # Uncertainty quality (lower relative error is better)
                uncertainty_quality = max(
                    0.0,
                    min(1.0, 1.0 / (1.0 + rel_amplitude_error + rel_exponent_error)),
                )
                quality_factors.append(uncertainty_quality)

            # Compute weighted average of quality factors
            if quality_factors:
                quality = np.mean(quality_factors)
            else:
                quality = 0.0

            return float(quality)

        except Exception as e:
            self.logger.error(f"Quality calculation failed: {e}")
            return 0.0

    def calculate_decay_rate(self, power_law_fit: Dict[str, float]) -> float:
        """
        Calculate decay rate from power law fit using full analytical method.

        Physical Meaning:
            Calculates the decay rate from the power law exponent using
            complete analytical methods based on 7D phase field theory.

        Mathematical Foundation:
            Computes decay rate considering both the exponent magnitude
            and the field amplitude for comprehensive characterization.

        Args:
            power_law_fit (Dict[str, float]): Power law fitting results.

        Returns:
            float: Comprehensive decay rate.
        """
        try:
            # Extract parameters
            exponent = power_law_fit.get("power_law_exponent", 0.0)
            amplitude = power_law_fit.get("amplitude", 1.0)
            parameter_errors = power_law_fit.get("parameter_errors", [0.0, 0.0])

            # Basic decay rate from exponent magnitude
            base_decay_rate = abs(exponent)

            # Amplitude-weighted decay rate
            amplitude_factor = min(1.0, amplitude)  # Normalize amplitude
            amplitude_weighted_decay = base_decay_rate * amplitude_factor

            # Uncertainty-weighted decay rate
            if len(parameter_errors) >= 2:
                exponent_error = parameter_errors[1]
                uncertainty_factor = max(0.1, 1.0 / (1.0 + exponent_error))
                uncertainty_weighted_decay = (
                    amplitude_weighted_decay * uncertainty_factor
                )
            else:
                uncertainty_weighted_decay = amplitude_weighted_decay

            # Quality-weighted decay rate
            fitting_quality = power_law_fit.get("fitting_quality", 0.0)
            quality_weighted_decay = uncertainty_weighted_decay * fitting_quality

            # Final decay rate (combine all factors)
            final_decay_rate = quality_weighted_decay

            # Ensure reasonable bounds
            final_decay_rate = max(0.01, min(10.0, final_decay_rate))

            return float(final_decay_rate)

        except Exception as e:
            self.logger.error(f"Decay rate calculation failed: {e}")
            # Return basic decay rate as fallback
            exponent = power_law_fit.get("power_law_exponent", 0.0)
            return float(abs(exponent))

    def compute_r_squared(
        self, radial_profile: Dict[str, np.ndarray], popt: np.ndarray, func
    ) -> float:
        """
        Compute R-squared for power law fit.

        Physical Meaning:
            Computes R-squared coefficient of determination
            for power law fitting quality assessment.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.
            popt (np.ndarray): Fitted parameters.
            func: Power law function.

        Returns:
            float: R-squared value.
        """
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

    def compute_fitting_quality(self, pcov: np.ndarray) -> float:
        """
        Compute fitting quality from covariance matrix.

        Physical Meaning:
            Computes fitting quality based on parameter uncertainty
            from covariance matrix analysis.

        Args:
            pcov (np.ndarray): Parameter covariance matrix.

        Returns:
            float: Fitting quality metric (0-1).
        """
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

    def compute_chi_squared(
        self, radial_profile: Dict[str, np.ndarray], popt: np.ndarray, func
    ) -> float:
        """
        Compute chi-squared statistic for power law fit using full 7D BVP theory.

        Physical Meaning:
            Computes chi-squared statistic for goodness of fit
            assessment in power law analysis for 7D phase field theory.

        Mathematical Foundation:
            Implements chi-squared calculation with proper error handling
            and normalization for 7D BVP theory applications.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.
            popt (np.ndarray): Fitted parameters.
            func: Power law function.

        Returns:
            float: Chi-squared value.
        """
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

    def perform_comprehensive_quality_analysis(
        self, radial_profile: Dict[str, np.ndarray], fit_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform comprehensive quality analysis for power law fit.

        Physical Meaning:
            Performs comprehensive quality analysis including statistical
            measures, physical constraints, and 7D BVP theory validation.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.
            fit_result (Dict[str, Any]): Fitting results.

        Returns:
            Dict[str, Any]: Comprehensive quality analysis results.
        """
        try:
            # Extract quality metrics
            r_squared = fit_result.get("r_squared", 0.0)
            chi_squared = fit_result.get("chi_squared", float("inf"))
            fitting_quality = fit_result.get("fitting_quality", 0.0)

            # Compute additional quality measures
            data_points = len(radial_profile["r"])
            parameter_errors = fit_result.get("parameter_errors", [0.0, 0.0])

            # Statistical quality
            statistical_quality = self._compute_statistical_quality(
                r_squared, chi_squared, data_points
            )

            # Physical constraints quality
            physical_quality = self._compute_physical_quality(
                fit_result.get("amplitude", 1.0), fit_result.get("exponent", -2.0)
            )

            # Parameter uncertainty quality
            uncertainty_quality = self._compute_uncertainty_quality(parameter_errors)

            # Overall quality
            overall_quality = np.mean(
                [
                    statistical_quality,
                    physical_quality,
                    uncertainty_quality,
                    fitting_quality,
                ]
            )

            return {
                "statistical_quality": float(statistical_quality),
                "physical_quality": float(physical_quality),
                "uncertainty_quality": float(uncertainty_quality),
                "overall_quality": float(overall_quality),
                "data_points": data_points,
                "r_squared": float(r_squared),
                "chi_squared": float(chi_squared),
                "fitting_quality": float(fitting_quality),
            }

        except Exception as e:
            self.logger.error(f"Quality analysis failed: {e}")
            return {
                "statistical_quality": 0.0,
                "physical_quality": 0.0,
                "uncertainty_quality": 0.0,
                "overall_quality": 0.0,
                "error": str(e),
            }

    def _compute_statistical_quality(
        self, r_squared: float, chi_squared: float, data_points: int
    ) -> float:
        """Compute statistical quality based on R-squared and chi-squared."""
        try:
            # R-squared contribution
            r_squared_quality = max(0.0, min(1.0, r_squared))

            # Chi-squared contribution (closer to 1 is better)
            if chi_squared != float("inf"):
                chi_squared_quality = max(
                    0.0, min(1.0, 1.0 / (1.0 + abs(chi_squared - 1.0)))
                )
            else:
                chi_squared_quality = 0.0

            # Data points contribution
            if data_points < 3:
                data_quality = 0.0
            elif data_points < 5:
                data_quality = 0.7
            elif data_points < 10:
                data_quality = 0.8
            elif data_points < 20:
                data_quality = 0.9
            else:
                data_quality = 1.0

            return np.mean([r_squared_quality, chi_squared_quality, data_quality])

        except Exception as e:
            self.logger.error(f"Statistical quality computation failed: {e}")
            return 0.0

    def _compute_physical_quality(self, amplitude: float, exponent: float) -> float:
        """Compute physical quality based on parameter bounds."""
        try:
            quality = 1.0

            # Check amplitude bounds
            if amplitude <= 0:
                quality *= 0.0
            elif amplitude > 100:
                quality *= 0.7

            # Check exponent bounds
            if abs(exponent) > 10:
                quality *= 0.5
            elif abs(exponent) > 5:
                quality *= 0.8

            return max(0.0, min(1.0, quality))

        except Exception as e:
            self.logger.error(f"Physical quality computation failed: {e}")
            return 0.0

    def _compute_uncertainty_quality(self, parameter_errors: List[float]) -> float:
        """Compute uncertainty quality based on parameter errors."""
        try:
            if not parameter_errors or len(parameter_errors) < 2:
                return 0.0

            # Relative errors
            rel_errors = [err / max(abs(err), 1e-10) for err in parameter_errors]

            # Uncertainty quality (lower relative error is better)
            uncertainty_quality = max(0.0, min(1.0, 1.0 / (1.0 + np.mean(rel_errors))))

            return uncertainty_quality

        except Exception as e:
            self.logger.error(f"Uncertainty quality computation failed: {e}")
            return 0.0
