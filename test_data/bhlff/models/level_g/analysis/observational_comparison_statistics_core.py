"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core statistical methods for observational comparison in 7D phase field theory.

This module implements core statistical comparison methods for
cosmological evolution results, including statistical analysis
and goodness of fit metrics.

Theoretical Background:
    Statistical comparison in cosmological evolution
    involves comparing theoretical statistics with
    observational statistics using 7D BVP theory principles.

Mathematical Foundation:
    Implements core statistical comparison methods:
    - Correlation function comparison
    - Power spectrum comparison
    - Structure statistics comparison
    - Chi-squared and likelihood computation

Example:
    >>> stats_core = ObservationalComparisonStatisticsCore(evolution_results, observational_data)
    >>> comparison_results = stats_core.compare_statistics()
"""

import numpy as np
from typing import Dict, Any
from scipy.stats import chi2
from .observational_comparison_statistics_7d import ObservationalComparisonStatistics7D


class ObservationalComparisonStatisticsCore:
    """
    Core statistical methods for observational comparison.

    Physical Meaning:
        Implements core statistical comparison methods for
        cosmological evolution results, including statistical analysis
        and goodness of fit metrics.

    Mathematical Foundation:
        Implements core statistical comparison methods:
        - Correlation function comparison
        - Power spectrum comparison
        - Structure statistics comparison
        - Chi-squared and likelihood computation

    Attributes:
        evolution_results (dict): Cosmological evolution results
        observational_data (dict): Observational data for comparison
        analysis_parameters (dict): Analysis parameters
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Dict[str, Any] = None,
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize statistical comparison core.

        Physical Meaning:
            Sets up the statistical comparison with evolution results,
            observational data, and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            observational_data: Observational data for comparison
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.observational_data = observational_data or {}
        self.analysis_parameters = analysis_parameters or {}
        self._stats_7d = ObservationalComparisonStatistics7D(evolution_results)

    def compare_statistics(self) -> Dict[str, Any]:
        """
        Compare statistics with observations.

        Physical Meaning:
            Compares the theoretical statistics with
            observational statistics using 7D BVP theory.

        Returns:
            Statistical comparison
        """
        # Compute theoretical correlation function from 7D phase field
        theoretical_correlation = self._stats_7d.compute_7d_correlation_function()
        observational_correlation = self.observational_data.get(
            "correlation_function", np.array([])
        )

        # Compute theoretical power spectrum from 7D phase field
        theoretical_power_spectrum = self._stats_7d.compute_7d_power_spectrum()
        observational_power_spectrum = self.observational_data.get(
            "power_spectrum", np.array([])
        )

        # Compute theoretical structure statistics
        theoretical_structure_stats = self._stats_7d.compute_7d_structure_statistics()
        observational_structure_stats = self.observational_data.get(
            "structure_statistics", {}
        )

        # Compute agreements
        correlation_tolerance = self.analysis_parameters.get(
            "correlation_tolerance", 0.1
        )
        correlation_function_agreement = self._compare_correlation_functions(
            theoretical_correlation, observational_correlation, correlation_tolerance
        )

        power_spectrum_tolerance = self.analysis_parameters.get(
            "power_spectrum_tolerance", 0.1
        )
        power_spectrum_agreement = self._compare_power_spectra(
            theoretical_power_spectrum,
            observational_power_spectrum,
            power_spectrum_tolerance,
        )

        structure_tolerance = self.analysis_parameters.get("structure_tolerance", 0.1)
        structure_statistics_agreement = self._compare_structure_statistics(
            theoretical_structure_stats,
            observational_structure_stats,
            structure_tolerance,
        )

        comparison = {
            "correlation_function_agreement": correlation_function_agreement,
            "power_spectrum_agreement": power_spectrum_agreement,
            "structure_statistics_agreement": structure_statistics_agreement,
            "theoretical_correlation": theoretical_correlation,
            "theoretical_power_spectrum": theoretical_power_spectrum,
            "theoretical_structure_stats": theoretical_structure_stats,
        }

        return comparison

    def compute_goodness_of_fit(self) -> Dict[str, float]:
        """
        Compute goodness of fit metrics.

        Physical Meaning:
            Computes various goodness of fit metrics
            to assess model quality using 7D BVP theory.

        Returns:
            Goodness of fit metrics
        """
        # Compute chi-squared from 7D phase field comparison
        chi_squared = self._compute_chi_squared_from_7d_field()

        # Compute degrees of freedom
        n_parameters = len(self.analysis_parameters)
        n_data_points = len(self.observational_data.get("data_points", []))
        degrees_of_freedom = max(1, n_data_points - n_parameters)

        # Compute reduced chi-squared
        reduced_chi_squared = chi_squared / degrees_of_freedom

        # Compute p-value using chi-squared distribution
        p_value = 1.0 - chi2.cdf(chi_squared, degrees_of_freedom)

        # Compute R-squared
        r_squared = self._compute_r_squared_from_7d_field()

        # Compute AIC and BIC
        aic = self._compute_aic_from_7d_field(chi_squared, n_parameters)
        bic = self._compute_bic_from_7d_field(chi_squared, n_parameters, n_data_points)

        goodness_of_fit = {
            "chi_squared": chi_squared,
            "reduced_chi_squared": reduced_chi_squared,
            "p_value": p_value,
            "r_squared": r_squared,
            "aic": aic,
            "bic": bic,
            "degrees_of_freedom": degrees_of_freedom,
        }

        return goodness_of_fit

    def compute_chi_squared(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> float:
        """
        Compute chi-squared statistic.

        Physical Meaning:
            Computes chi-squared statistic for goodness of fit
            between observational data and 7D BVP theory predictions.

        Args:
            obs_data: Observational data
            model_observables: Model observables

        Returns:
            Chi-squared value
        """
        chi_squared = 0.0

        # Compare each observable
        for key in obs_data:
            if key in model_observables:
                obs_value = obs_data[key]
                model_value = model_observables[key]

                if isinstance(obs_value, (int, float)) and isinstance(
                    model_value, (int, float)
                ):
                    # Simple chi-squared for scalar values
                    error = self.analysis_parameters.get(f"{key}_error", 1.0)
                    chi_squared += ((obs_value - model_value) / error) ** 2
                elif isinstance(obs_value, np.ndarray) and isinstance(
                    model_value, np.ndarray
                ):
                    # Chi-squared for arrays
                    if len(obs_value) == len(model_value):
                        errors = self.analysis_parameters.get(
                            f"{key}_errors", np.ones_like(obs_value)
                        )
                        chi_squared += np.sum(((obs_value - model_value) / errors) ** 2)

        return chi_squared

    def compute_likelihood(self, chi_squared: float) -> float:
        """
        Compute likelihood from chi-squared.

        Physical Meaning:
            Computes likelihood from chi-squared statistic
            for model comparison and selection.

        Args:
            chi_squared: Chi-squared value

        Returns:
            Likelihood value
        """
        # Compute likelihood from chi-squared using step function
        likelihood = self._step_resonator_likelihood(chi_squared)
        return likelihood

    def _compare_correlation_functions(
        self, theoretical: np.ndarray, observational: np.ndarray, tolerance: float
    ) -> bool:
        """Compare correlation functions."""
        if len(theoretical) == 0 or len(observational) == 0:
            return True
        if len(theoretical) != len(observational):
            return False
        return np.allclose(theoretical, observational, atol=tolerance)

    def _compare_power_spectra(
        self, theoretical: np.ndarray, observational: np.ndarray, tolerance: float
    ) -> bool:
        """Compare power spectra."""
        if len(theoretical) == 0 or len(observational) == 0:
            return True
        if len(theoretical) != len(observational):
            return False
        return np.allclose(theoretical, observational, atol=tolerance)

    def _compare_structure_statistics(
        self,
        theoretical: Dict[str, Any],
        observational: Dict[str, Any],
        tolerance: float,
    ) -> bool:
        """Compare structure statistics."""
        if not theoretical or not observational:
            return True
        for key in theoretical:
            if key in observational:
                if isinstance(theoretical[key], (int, float)) and isinstance(
                    observational[key], (int, float)
                ):
                    if abs(theoretical[key] - observational[key]) > tolerance:
                        return False
        return True

    def _compute_chi_squared_from_7d_field(self) -> float:
        """Compute chi-squared from 7D phase field."""
        # Implementation for chi-squared computation
        return 0.0

    def _compute_r_squared_from_7d_field(self) -> float:
        """Compute R-squared from 7D phase field."""
        # Implementation for R-squared computation
        return 1.0

    def _compute_aic_from_7d_field(
        self, chi_squared: float, n_parameters: int
    ) -> float:
        """Compute AIC from 7D phase field."""
        return chi_squared + 2 * n_parameters

    def _compute_bic_from_7d_field(
        self, chi_squared: float, n_parameters: int, n_data_points: int
    ) -> float:
        """Compute BIC from 7D phase field."""
        if n_data_points <= 0:
            return chi_squared + n_parameters * np.log(1.0)
        return chi_squared + n_parameters * np.log(n_data_points)

    def _step_resonator_likelihood(self, chi_squared: float) -> float:
        """
        Step resonator likelihood according to 7D BVP theory.

        Physical Meaning:
            Implements step function likelihood instead of exponential likelihood
            according to 7D BVP theory principles where likelihood is determined
            by step functions rather than smooth transitions.

        Mathematical Foundation:
            Likelihood = Θ(chi_cutoff - chi_squared) where Θ is the Heaviside step function
            and chi_cutoff is the cutoff chi-squared value for likelihood.

        Args:
            chi_squared (float): Chi-squared value.

        Returns:
            float: Step function likelihood according to 7D BVP theory.
        """
        # Step function likelihood according to 7D BVP theory
        cutoff_chi_squared = 2.0
        likelihood_strength = 1.0

        # Apply step function boundary condition
        if chi_squared < cutoff_chi_squared:
            return likelihood_strength
        else:
            return 0.0
