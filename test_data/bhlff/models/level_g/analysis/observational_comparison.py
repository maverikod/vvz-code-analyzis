"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Observational comparison for cosmological analysis in 7D phase field theory.

This module implements observational comparison methods for
cosmological evolution results, including comparison with
observational data and goodness of fit analysis.

Theoretical Background:
    Observational comparison in cosmological evolution
    involves comparing theoretical results with observational
    data to validate the model using 7D BVP theory principles.

Mathematical Foundation:
    Implements observational comparison methods:
    - Structure formation comparison: with observational data
    - Parameter comparison: with observational constraints
    - Statistical comparison: with observational statistics
    - Goodness of fit: various goodness of fit metrics

Example:
    >>> comparison = ObservationalComparison(evolution_results, observational_data)
    >>> comparison_results = comparison.compare_with_observations()
"""

from typing import Dict, Any
from .observational_comparison_core import ObservationalComparisonCore


class ObservationalComparison:
    """
    Observational comparison for cosmological analysis.

    Physical Meaning:
        Implements observational comparison methods for
        cosmological evolution results, including comparison
        with observational data and goodness of fit analysis.

    Mathematical Foundation:
        Implements observational comparison methods:
        - Structure formation comparison: with observational data
        - Parameter comparison: with observational constraints
        - Statistical comparison: with observational statistics
        - Goodness of fit: various goodness of fit metrics

    Attributes:
        evolution_results (dict): Cosmological evolution results
        observational_data (dict): Observational data for comparison
        analysis_parameters (dict): Analysis parameters
        _core (ObservationalComparisonCore): Core implementation
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Dict[str, Any] = None,
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize observational comparison.

        Physical Meaning:
            Sets up the observational comparison with evolution results,
            observational data, and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            observational_data: Observational data for comparison
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.observational_data = observational_data or {}
        self.analysis_parameters = analysis_parameters or {}
        self._core = ObservationalComparisonCore(
            evolution_results, observational_data, analysis_parameters
        )

    def compare_with_observations(self) -> Dict[str, Any]:
        """
        Compare results with observational data.

        Physical Meaning:
            Compares the theoretical results with observational
            data to validate the model using 7D BVP theory principles.

        Returns:
            Comparison results
        """
        return self._core.compare_with_observations()
