"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Parameter evolution analysis for cosmological analysis in 7D phase field theory.

This module implements parameter evolution analysis methods for
cosmological evolution results, including parameter trends,
evolution rates, and stability analysis.

Theoretical Background:
    Parameter evolution analysis in cosmological evolution
    involves analyzing how cosmological parameters evolve
    over time and their impact on structure formation.

Mathematical Foundation:
    Implements parameter evolution analysis methods:
    - Parameter trends: based on parameter evolution
    - Evolution rates: based on parameter derivatives
    - Stability analysis: based on parameter stability

Example:
    >>> analysis = ParameterAnalysis(evolution_results)
    >>> parameter_trends = analysis.analyze_parameter_evolution()
"""

import numpy as np
from typing import Dict, Any, List, Optional


class ParameterAnalysis:
    """
    Parameter evolution analysis for cosmological analysis.

    Physical Meaning:
        Implements parameter evolution analysis methods for
        cosmological evolution results, including parameter
        trends, evolution rates, and stability analysis.

    Mathematical Foundation:
        Implements parameter evolution analysis methods:
        - Parameter trends: based on parameter evolution
        - Evolution rates: based on parameter derivatives
        - Stability analysis: based on parameter stability

    Attributes:
        evolution_results (dict): Cosmological evolution results
        analysis_parameters (dict): Analysis parameters
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize parameter analysis.

        Physical Meaning:
            Sets up the parameter analysis with evolution results
            and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.analysis_parameters = analysis_parameters or {}

    def analyze_parameter_evolution(self) -> Dict[str, Any]:
        """
        Analyze parameter evolution over time.

        Physical Meaning:
            Analyzes how cosmological parameters evolve
            over cosmological time.

        Returns:
            Parameter evolution analysis
        """
        if not self.evolution_results:
            return {}

        # Analyze parameter evolution
        analysis = {
            "scale_factor_evolution": self._analyze_scale_factor_evolution(),
            "hubble_parameter_evolution": self._analyze_hubble_parameter_evolution(),
            "parameter_trends": self._compute_parameter_trends(),
            "parameter_stability": self._analyze_parameter_stability(),
        }

        return analysis

    def _analyze_scale_factor_evolution(self) -> Dict[str, Any]:
        """
        Analyze scale factor evolution.

        Physical Meaning:
            Analyzes how the scale factor evolves over
            cosmological time.

        Returns:
            Scale factor evolution analysis
        """
        scale_factor = self.evolution_results.get("scale_factor", [])
        if len(scale_factor) == 0:
            return {}

        # Compute scale factor metrics
        scale_analysis = {
            "initial_scale_factor": scale_factor[0],
            "final_scale_factor": scale_factor[-1],
            "scale_factor_growth": scale_factor[-1] - scale_factor[0],
            "scale_factor_rate": self._compute_scale_factor_rate(scale_factor),
            "scale_factor_acceleration": self._compute_scale_factor_acceleration(
                scale_factor
            ),
        }

        return scale_analysis

    def _compute_scale_factor_rate(self, scale_factor: List[float]) -> float:
        """
        Compute scale factor evolution rate.

        Physical Meaning:
            Computes the rate of change of the scale factor
            over cosmological time.

        Args:
            scale_factor: Scale factor evolution

        Returns:
            Scale factor rate
        """
        if len(scale_factor) < 2:
            return 0.0

        # Compute rate of change
        rate = np.mean(np.diff(scale_factor))
        return float(rate)

    def _compute_scale_factor_acceleration(self, scale_factor: List[float]) -> float:
        """
        Compute scale factor acceleration.

        Physical Meaning:
            Computes the acceleration of the scale factor
            over cosmological time.

        Args:
            scale_factor: Scale factor evolution

        Returns:
            Scale factor acceleration
        """
        if len(scale_factor) < 3:
            return 0.0

        # Compute second derivative
        acceleration = np.mean(np.diff(np.diff(scale_factor)))
        return float(acceleration)

    def _analyze_hubble_parameter_evolution(self) -> Dict[str, Any]:
        """
        Analyze Hubble parameter evolution.

        Physical Meaning:
            Analyzes how the Hubble parameter evolves over
            cosmological time.

        Returns:
            Hubble parameter evolution analysis
        """
        hubble_parameter = self.evolution_results.get("hubble_parameter", [])
        if len(hubble_parameter) == 0:
            return {}

        # Compute Hubble parameter metrics
        hubble_analysis = {
            "initial_hubble_parameter": hubble_parameter[0],
            "final_hubble_parameter": hubble_parameter[-1],
            "hubble_parameter_change": hubble_parameter[-1] - hubble_parameter[0],
            "hubble_parameter_rate": self._compute_hubble_parameter_rate(
                hubble_parameter
            ),
            "hubble_parameter_stability": self._compute_hubble_parameter_stability(
                hubble_parameter
            ),
        }

        return hubble_analysis

    def _compute_hubble_parameter_rate(self, hubble_parameter: List[float]) -> float:
        """
        Compute Hubble parameter evolution rate.

        Physical Meaning:
            Computes the rate of change of the Hubble parameter
            over cosmological time.

        Args:
            hubble_parameter: Hubble parameter evolution

        Returns:
            Hubble parameter rate
        """
        if len(hubble_parameter) < 2:
            return 0.0

        # Compute rate of change
        rate = np.mean(np.diff(hubble_parameter))
        return float(rate)

    def _compute_hubble_parameter_stability(
        self, hubble_parameter: List[float]
    ) -> float:
        """
        Compute Hubble parameter stability.

        Physical Meaning:
            Computes the stability of the Hubble parameter
            over cosmological time.

        Args:
            hubble_parameter: Hubble parameter evolution

        Returns:
            Hubble parameter stability
        """
        if len(hubble_parameter) < 2:
            return 0.0

        # Compute stability as inverse of variance
        stability = 1.0 / (np.var(hubble_parameter) + 1e-10)
        return float(stability)

    def _compute_parameter_trends(self) -> Dict[str, Any]:
        """
        Compute parameter trends.

        Physical Meaning:
            Computes trends in cosmological parameters
            over cosmological time.

        Returns:
            Parameter trends
        """
        scale_factor = self.evolution_results.get("scale_factor", [])
        hubble_parameter = self.evolution_results.get("hubble_parameter", [])

        trends = {
            "scale_factor_trend": self._compute_trend(scale_factor),
            "hubble_parameter_trend": self._compute_trend(hubble_parameter),
            "parameter_correlation": self._compute_parameter_correlation(
                scale_factor, hubble_parameter
            ),
        }

        return trends

    def _compute_trend(self, values: List[float]) -> str:
        """
        Compute trend in values.

        Physical Meaning:
            Computes the trend (increasing, decreasing, stable)
            in a set of values.

        Args:
            values: List of values

        Returns:
            Trend description
        """
        if len(values) < 2:
            return "stable"

        # Compute trend
        if values[-1] > values[0]:
            return "increasing"
        elif values[-1] < values[0]:
            return "decreasing"
        else:
            return "stable"

    def _compute_parameter_correlation(
        self, scale_factor: List[float], hubble_parameter: List[float]
    ) -> float:
        """
        Compute correlation between parameters.

        Physical Meaning:
            Computes the correlation between scale factor
            and Hubble parameter evolution.

        Args:
            scale_factor: Scale factor evolution
            hubble_parameter: Hubble parameter evolution

        Returns:
            Parameter correlation
        """
        if len(scale_factor) != len(hubble_parameter) or len(scale_factor) < 2:
            return 0.0

        # Compute correlation
        correlation = np.corrcoef(scale_factor, hubble_parameter)[0, 1]
        if np.isnan(correlation):
            return 0.0

        return float(correlation)

    def _analyze_parameter_stability(self) -> Dict[str, Any]:
        """
        Analyze parameter stability.

        Physical Meaning:
            Analyzes the stability of cosmological parameters
            over cosmological time.

        Returns:
            Parameter stability analysis
        """
        scale_factor = self.evolution_results.get("scale_factor", [])
        hubble_parameter = self.evolution_results.get("hubble_parameter", [])

        stability_analysis = {
            "scale_factor_stability": self._compute_parameter_stability(scale_factor),
            "hubble_parameter_stability": self._compute_parameter_stability(
                hubble_parameter
            ),
            "overall_stability": self._compute_overall_stability(
                scale_factor, hubble_parameter
            ),
        }

        return stability_analysis

    def _compute_parameter_stability(self, values: List[float]) -> float:
        """
        Compute parameter stability.

        Physical Meaning:
            Computes the stability of a parameter over time.

        Args:
            values: Parameter values

        Returns:
            Parameter stability
        """
        if len(values) < 2:
            return 0.0

        # Compute stability as inverse of coefficient of variation
        mean_val = np.mean(values)
        std_val = np.std(values)

        if mean_val == 0:
            return 0.0

        stability = mean_val / (std_val + 1e-10)
        return float(stability)

    def _compute_overall_stability(
        self, scale_factor: List[float], hubble_parameter: List[float]
    ) -> float:
        """
        Compute overall parameter stability.

        Physical Meaning:
            Computes the overall stability of all parameters.

        Args:
            scale_factor: Scale factor evolution
            hubble_parameter: Hubble parameter evolution

        Returns:
            Overall stability
        """
        scale_stability = self._compute_parameter_stability(scale_factor)
        hubble_stability = self._compute_parameter_stability(hubble_parameter)

        # Overall stability as average
        overall_stability = (scale_stability + hubble_stability) / 2.0
        return float(overall_stability)
