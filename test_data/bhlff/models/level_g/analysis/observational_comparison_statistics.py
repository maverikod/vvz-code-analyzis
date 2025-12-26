"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical methods for observational comparison in 7D phase field theory.

This module implements statistical comparison methods for
cosmological evolution results, including statistical analysis
and goodness of fit metrics.

Theoretical Background:
    Statistical comparison in cosmological evolution
    involves comparing theoretical statistics with
    observational statistics using 7D BVP theory principles.

Mathematical Foundation:
    Implements statistical comparison methods:
    - Correlation function comparison
    - Power spectrum comparison
    - Structure statistics comparison
    - Chi-squared and likelihood computation

Example:
    >>> stats = ObservationalComparisonStatistics(evolution_results, observational_data)
    >>> comparison_results = stats.compare_statistics()
"""

from typing import Dict, Any
from .observational_comparison_statistics_core import (
    ObservationalComparisonStatisticsCore,
)


class ObservationalComparisonStatistics:
    """
    Statistical methods for observational comparison.

    Physical Meaning:
        Implements statistical comparison methods for
        cosmological evolution results, including statistical analysis
        and goodness of fit metrics.

    Mathematical Foundation:
        Implements statistical comparison methods:
        - Correlation function comparison
        - Power spectrum comparison
        - Structure statistics comparison
        - Chi-squared and likelihood computation

    Attributes:
        evolution_results (dict): Cosmological evolution results
        observational_data (dict): Observational data for comparison
        analysis_parameters (dict): Analysis parameters
        _core (ObservationalComparisonStatisticsCore): Core implementation
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Dict[str, Any] = None,
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize statistical comparison.

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
        self._core = ObservationalComparisonStatisticsCore(
            evolution_results, observational_data, analysis_parameters
        )

    def compare_statistics(self) -> Dict[str, Any]:
        """
        Compare statistics with observations.

        Physical Meaning:
            Compares the theoretical statistics with
            observational statistics using 7D BVP theory.

        Returns:
            Statistical comparison
        """
        return self._core.compare_statistics()

    def compute_goodness_of_fit(self) -> Dict[str, float]:
        """
        Compute goodness of fit metrics.

        Physical Meaning:
            Computes various goodness of fit metrics
            to assess model quality using 7D BVP theory.

        Returns:
            Goodness of fit metrics
        """
        return self._core.compute_goodness_of_fit()

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
        return self._core.compute_chi_squared(obs_data, model_observables)

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
        return self._core.compute_likelihood(chi_squared)
