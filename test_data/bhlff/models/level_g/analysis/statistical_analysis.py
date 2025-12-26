"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical analysis for cosmological analysis in 7D phase field theory.

This module implements statistical analysis methods for
cosmological evolution results, including structure statistics,
correlation analysis, and statistical metrics.

Theoretical Background:
    Statistical analysis in cosmological evolution
    involves analyzing statistical properties of structure formation,
    including mean, variance, and correlation properties.

Mathematical Foundation:
    Implements statistical analysis methods:
    - Structure statistics: mean, variance, skewness, kurtosis
    - Correlation analysis: Pearson correlation coefficients
    - Statistical metrics: various statistical measures

Example:
    >>> analysis = StatisticalAnalysis(evolution_results)
    >>> statistics = analysis.compute_structure_statistics()
"""

import numpy as np
from typing import Dict, Any, List, Optional


class StatisticalAnalysis:
    """
    Statistical analysis for cosmological analysis.

    Physical Meaning:
        Implements statistical analysis methods for
        cosmological evolution results, including structure
        statistics, correlation analysis, and statistical metrics.

    Mathematical Foundation:
        Implements statistical analysis methods:
        - Structure statistics: mean, variance, skewness, kurtosis
        - Correlation analysis: Pearson correlation coefficients
        - Statistical metrics: various statistical measures

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
        Initialize statistical analysis.

        Physical Meaning:
            Sets up the statistical analysis with evolution results
            and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.analysis_parameters = analysis_parameters or {}

    def compute_structure_statistics(self) -> Dict[str, Any]:
        """
        Compute structure statistics.

        Physical Meaning:
            Computes statistical properties of structure formation,
            including mean, variance, and correlation properties.

        Returns:
            Structure statistics
        """
        structure_formation = self.evolution_results.get("structure_formation", [])
        if len(structure_formation) == 0:
            return {}

        # Extract structure metrics
        rms_values = [
            structure.get("phase_field_rms", 0.0) for structure in structure_formation
        ]
        max_values = [
            structure.get("phase_field_max", 0.0) for structure in structure_formation
        ]
        correlation_values = [
            structure.get("correlation_length", 0.0)
            for structure in structure_formation
        ]

        # Compute statistics
        statistics = {
            "rms_mean": np.mean(rms_values),
            "rms_std": np.std(rms_values),
            "rms_min": np.min(rms_values),
            "rms_max": np.max(rms_values),
            "max_mean": np.mean(max_values),
            "max_std": np.std(max_values),
            "correlation_mean": np.mean(correlation_values),
            "correlation_std": np.std(correlation_values),
            "structure_variance": np.var(rms_values),
            "structure_skewness": self._compute_skewness(rms_values),
            "structure_kurtosis": self._compute_kurtosis(rms_values),
        }

        return statistics

    def _compute_skewness(self, values: List[float]) -> float:
        """
        Compute skewness of values.

        Physical Meaning:
            Computes the skewness (third moment) of the
            structure values.

        Args:
            values: List of values

        Returns:
            Skewness
        """
        if len(values) < 3:
            return 0.0

        mean_val = np.mean(values)
        std_val = np.std(values)

        if std_val == 0:
            return 0.0

        skewness = np.mean([(x - mean_val) ** 3 for x in values]) / (std_val**3)
        return float(skewness)

    def _compute_kurtosis(self, values: List[float]) -> float:
        """
        Compute kurtosis of values.

        Physical Meaning:
            Computes the kurtosis (fourth moment) of the
            structure values.

        Args:
            values: List of values

        Returns:
            Kurtosis
        """
        if len(values) < 4:
            return 0.0

        mean_val = np.mean(values)
        std_val = np.std(values)

        if std_val == 0:
            return 0.0

        kurtosis = np.mean([(x - mean_val) ** 4 for x in values]) / (std_val**4) - 3
        return float(kurtosis)

    def analyze_correlations(self) -> Dict[str, Any]:
        """
        Analyze correlations in structure formation.

        Physical Meaning:
            Analyzes correlations between different structure
            metrics and evolution parameters.

        Returns:
            Correlation analysis
        """
        structure_formation = self.evolution_results.get("structure_formation", [])
        if len(structure_formation) == 0:
            return {}

        # Extract metrics
        rms_values = [
            structure.get("phase_field_rms", 0.0) for structure in structure_formation
        ]
        max_values = [
            structure.get("phase_field_max", 0.0) for structure in structure_formation
        ]
        correlation_values = [
            structure.get("correlation_length", 0.0)
            for structure in structure_formation
        ]
        time_values = [structure["time"] for structure in structure_formation]

        # Compute correlations
        correlations = {
            "rms_time_correlation": self._compute_correlation(rms_values, time_values),
            "max_time_correlation": self._compute_correlation(max_values, time_values),
            "correlation_time_correlation": self._compute_correlation(
                correlation_values, time_values
            ),
            "rms_max_correlation": self._compute_correlation(rms_values, max_values),
            "rms_correlation_correlation": self._compute_correlation(
                rms_values, correlation_values
            ),
            "max_correlation_correlation": self._compute_correlation(
                max_values, correlation_values
            ),
        }

        return correlations

    def _compute_correlation(self, x: List[float], y: List[float]) -> float:
        """
        Compute correlation coefficient.

        Physical Meaning:
            Computes the Pearson correlation coefficient
            between two sets of values.

        Args:
            x: First set of values
            y: Second set of values

        Returns:
            Correlation coefficient
        """
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        # Compute correlation coefficient
        x_array = np.array(x)
        y_array = np.array(y)

        correlation = np.corrcoef(x_array, y_array)[0, 1]

        if np.isnan(correlation):
            return 0.0

        return float(correlation)
