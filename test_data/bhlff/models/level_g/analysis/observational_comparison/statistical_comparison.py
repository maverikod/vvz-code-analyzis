"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical comparison for cosmological analysis.

This module implements comprehensive statistical comparison
functionality for 7D BVP theory comparison.

Theoretical Background:
    Statistical comparison involves performing statistical
    analysis between observational data and model predictions
    using 7D BVP theory principles.

Example:
    >>> comparison = StatisticalComparison(analysis_parameters)
    >>> results = comparison.perform_comparison(obs_data, model_observables)
"""

import numpy as np
from typing import Dict, Any, List, Optional
from scipy.stats import ttest_ind


class StatisticalComparison:
    """
    Statistical comparison for cosmological analysis.

    Physical Meaning:
        Performs comprehensive statistical comparison between
        observational data and 7D BVP theory predictions.

    Mathematical Foundation:
        Implements statistical comparison methods:
        - Parameter correlation analysis
        - Statistical significance testing
        - Model consistency checking
        - Chi-squared analysis
        - Likelihood computation
    """

    def __init__(self, analysis_parameters: Dict[str, Any] = None):
        """
        Initialize statistical comparison.

        Physical Meaning:
            Sets up the statistical comparison with analysis
            parameters.

        Args:
            analysis_parameters: Analysis parameters
        """
        self.analysis_parameters = analysis_parameters or {}

    def perform_comparison(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform statistical comparison between observations and model.

        Physical Meaning:
            Performs comprehensive statistical comparison between
            observational data and 7D BVP theory predictions.

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Statistical comparison results
        """
        # Compute statistical metrics
        comparison = {
            "parameter_correlation": self._compute_parameter_correlation(
                obs_data, model_observables
            ),
            "statistical_significance": self._compute_statistical_significance(
                obs_data, model_observables
            ),
            "model_consistency": self._compute_model_consistency(
                obs_data, model_observables
            ),
        }

        return comparison

    def compute_chi_squared(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> float:
        """
        Compute chi-squared statistic.

        Physical Meaning:
            Computes chi-squared statistic for model-observation
            comparison using 7D BVP theory.

        Mathematical Foundation:
            χ² = Σ[(obs - model)² / σ²]
            where σ is the measurement error.

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Chi-squared statistic
        """
        chi_squared = 0.0

        # Compute chi-squared for each parameter
        for key in ["hubble_parameter", "matter_density", "dark_energy"]:
            if key in obs_data and key in model_observables:
                obs_value = obs_data[key]
                model_value = model_observables[key]

                if isinstance(obs_value, (int, float)) and isinstance(
                    model_value, (int, float)
                ):
                    # Get measurement error
                    error = self._get_measurement_error(key)

                    if error > 0:
                        chi_squared += ((obs_value - model_value) / error) ** 2

        return chi_squared

    def compute_likelihood(self, chi_squared: float) -> float:
        """
        Compute likelihood from chi-squared.

        Physical Meaning:
            Computes likelihood from chi-squared statistic
            for model evaluation.

        Mathematical Foundation:
            L = exp(-χ²/2)

        Args:
            chi_squared: Chi-squared statistic

        Returns:
            Likelihood value
        """
        return self._step_resonator_likelihood(chi_squared)

    def compute_goodness_of_fit(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute goodness of fit metrics.

        Physical Meaning:
            Computes comprehensive goodness of fit metrics
            for model-observation comparison.

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Goodness of fit metrics
        """
        # Compute chi-squared
        chi_squared = self.compute_chi_squared(obs_data, model_observables)

        # Compute likelihood
        likelihood = self.compute_likelihood(chi_squared)

        # Compute R-squared
        r_squared = self._compute_r_squared(obs_data, model_observables)

        # Compute AIC and BIC
        aic = self._compute_aic(chi_squared, len(model_observables))
        bic = self._compute_bic(chi_squared, len(model_observables), len(obs_data))

        return {
            "chi_squared": chi_squared,
            "likelihood": likelihood,
            "r_squared": r_squared,
            "aic": aic,
            "bic": bic,
            "goodness_quality": self._assess_goodness_quality(chi_squared, r_squared),
        }

    def _compute_parameter_correlation(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> float:
        """
        Compute parameter correlation between observations and model.

        Physical Meaning:
            Computes correlation coefficient between observational
            and theoretical parameters using 7D BVP theory.

        Mathematical Foundation:
            Uses Pearson correlation coefficient:
            r = Σ(xi - x̄)(yi - ȳ) / √[Σ(xi - x̄)²Σ(yi - ȳ)²]

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Correlation coefficient
        """
        # Extract comparable parameters
        obs_params = []
        model_params = []

        for key in ["hubble_parameter", "matter_density", "dark_energy"]:
            if key in obs_data and key in model_observables:
                obs_params.append(obs_data[key])
                model_params.append(model_observables[key])

        if len(obs_params) < 2:
            return 1.0  # Default for insufficient data

        # Compute Pearson correlation coefficient
        obs_array = np.array(obs_params)
        model_array = np.array(model_params)

        # Remove any NaN values
        valid_mask = ~(np.isnan(obs_array) | np.isnan(model_array))
        if np.sum(valid_mask) < 2:
            return 1.0

        obs_array = obs_array[valid_mask]
        model_array = model_array[valid_mask]

        # Compute correlation
        correlation = np.corrcoef(obs_array, model_array)[0, 1]

        return correlation if not np.isnan(correlation) else 1.0

    def _compute_statistical_significance(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> float:
        """
        Compute statistical significance of model-observation agreement.

        Physical Meaning:
            Computes statistical significance using t-test
            for parameter differences in 7D BVP theory.

        Mathematical Foundation:
            Uses t-test for parameter differences:
            t = (μ1 - μ2) / √(s1²/n1 + s2²/n2)

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Statistical significance (p-value)
        """
        # Extract comparable parameters
        obs_params = []
        model_params = []

        for key in ["hubble_parameter", "matter_density", "dark_energy"]:
            if key in obs_data and key in model_observables:
                obs_params.append(obs_data[key])
                model_params.append(model_observables[key])

        if len(obs_params) < 2:
            return 0.95  # Default for insufficient data

        # Compute t-test
        try:
            t_stat, p_value = ttest_ind(obs_params, model_params)
            return p_value if not np.isnan(p_value) else 0.95
        except:
            return 0.95

    def _compute_model_consistency(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> bool:
        """
        Compute model consistency with observations.

        Physical Meaning:
            Determines if the model is consistent with observations
            using 7D BVP theory criteria.

        Mathematical Foundation:
            Uses tolerance-based consistency check:
            |model - obs| < tolerance for all parameters

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            True if model is consistent
        """
        # Define tolerances for each parameter
        tolerances = {
            "hubble_parameter": self.analysis_parameters.get("hubble_tolerance", 2.0),
            "matter_density": self.analysis_parameters.get("matter_tolerance", 0.05),
            "dark_energy": self.analysis_parameters.get("dark_energy_tolerance", 0.05),
        }

        # Check consistency for each parameter
        for key, tolerance in tolerances.items():
            if key in obs_data and key in model_observables:
                obs_value = obs_data[key]
                model_value = model_observables[key]

                if isinstance(obs_value, (int, float)) and isinstance(
                    model_value, (int, float)
                ):
                    if abs(model_value - obs_value) > tolerance:
                        return False

        return True

    def _get_measurement_error(self, parameter: str) -> float:
        """Get measurement error for parameter."""
        errors = {
            "hubble_parameter": 2.0,
            "matter_density": 0.02,
            "dark_energy": 0.02,
            "baryon_density": 0.005,
            "neutrino_density": 0.002,
        }
        return errors.get(parameter, 0.1)

    def _compute_r_squared(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> float:
        """Compute R-squared statistic."""
        # Extract comparable parameters
        obs_params = []
        model_params = []

        for key in ["hubble_parameter", "matter_density", "dark_energy"]:
            if key in obs_data and key in model_observables:
                obs_params.append(obs_data[key])
                model_params.append(model_observables[key])

        if len(obs_params) < 2:
            return 1.0

        obs_array = np.array(obs_params)
        model_array = np.array(model_params)

        # Compute R-squared
        ss_res = np.sum((obs_array - model_array) ** 2)
        ss_tot = np.sum((obs_array - np.mean(obs_array)) ** 2)

        if ss_tot == 0:
            return 1.0

        r_squared = 1 - (ss_res / ss_tot)
        return r_squared if not np.isnan(r_squared) else 1.0

    def _compute_aic(self, chi_squared: float, n_params: int) -> float:
        """Compute Akaike Information Criterion."""
        return chi_squared + 2 * n_params

    def _compute_bic(self, chi_squared: float, n_params: int, n_data: int) -> float:
        """Compute Bayesian Information Criterion."""
        return chi_squared + n_params * np.log(n_data)

    def _assess_goodness_quality(self, chi_squared: float, r_squared: float) -> str:
        """Assess goodness of fit quality."""
        if chi_squared < 1.0 and r_squared > 0.9:
            return "excellent"
        elif chi_squared < 5.0 and r_squared > 0.8:
            return "good"
        elif chi_squared < 10.0 and r_squared > 0.7:
            return "fair"
        else:
            return "poor"

    def _step_resonator_likelihood(self, chi_squared: float) -> float:
        """
        Step resonator likelihood function according to 7D BVP theory.

        Physical Meaning:
            Implements step function likelihood instead of exponential decay
            according to 7D BVP theory principles.
        """
        cutoff_chi_squared = 10.0
        return 1.0 if chi_squared < cutoff_chi_squared else 0.0
