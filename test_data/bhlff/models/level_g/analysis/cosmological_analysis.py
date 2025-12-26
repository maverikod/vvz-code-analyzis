"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main cosmological analysis for 7D phase field theory.

This module implements the main cosmological analysis that
coordinates the analysis of cosmological evolution results,
including structure formation, parameter evolution, and
observational comparison.

Theoretical Background:
    The cosmological analysis module provides tools for analyzing
    the results of cosmological evolution, including structure
    formation metrics and parameter evolution.

Mathematical Foundation:
    Implements statistical analysis methods for cosmological
    evolution results and structure formation metrics.

Example:
    >>> analysis = CosmologicalAnalysis(evolution_results, observational_data)
    >>> structure_analysis = analysis.analyze_structure_formation()
"""

import numpy as np
from typing import Dict, Any, List, Optional
from ...base.model_base import ModelBase
from .structure_analysis import StructureAnalysis
from .parameter_analysis import ParameterAnalysis
from .statistical_analysis import StatisticalAnalysis
from .observational_comparison import ObservationalComparisonCore


class CosmologicalAnalysis(ModelBase):
    """
    Main cosmological analysis for 7D phase field theory.

    Physical Meaning:
        Provides analysis tools for cosmological evolution results,
        including structure formation analysis and parameter evolution.

    Mathematical Foundation:
        Implements statistical analysis methods for cosmological
        evolution results and structure formation metrics.

    Attributes:
        evolution_results (dict): Cosmological evolution results
        analysis_results (dict): Analysis results
        observational_data (dict): Observational data for comparison
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize cosmological analysis.

        Physical Meaning:
            Sets up the cosmological analysis with evolution results
            and optional observational data for comparison.

        Args:
            evolution_results: Cosmological evolution results
            observational_data: Optional observational data
        """
        super().__init__()
        self.evolution_results = evolution_results
        self.observational_data = observational_data or {}
        self.analysis_results = {}

        # Initialize specialized components
        self.structure_analysis = StructureAnalysis(evolution_results)
        self.parameter_analysis = ParameterAnalysis(evolution_results)
        self.statistical_analysis = StatisticalAnalysis(evolution_results)
        self.observational_comparison = ObservationalComparison(
            evolution_results, observational_data
        )

        self._setup_analysis_parameters()

    def _setup_analysis_parameters(self) -> None:
        """
        Setup analysis parameters.

        Physical Meaning:
            Initializes parameters for cosmological analysis,
            including statistical methods and comparison metrics.
        """
        # Analysis parameters
        self.correlation_threshold = 0.1
        self.significance_level = 0.05
        self.structure_threshold = 0.5

        # Observational parameters
        self.observational_redshift_range = [0.0, 6.0]
        self.observational_scale_range = [0.1, 1000.0]  # Mpc

        # Statistical parameters
        self.bootstrap_samples = 1000
        self.confidence_level = 0.95

    def analyze_structure_formation(self) -> Dict[str, Any]:
        """
        Analyze structure formation process.

        Physical Meaning:
            Analyzes the process of structure formation from
            phase field evolution and gravitational effects.

        Returns:
            Structure formation analysis
        """
        if not self.evolution_results:
            return {}

        # Use structure analysis component
        return self.structure_analysis.analyze_structure_formation()

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

        # Use parameter analysis component
        return self.parameter_analysis.analyze_parameter_evolution()

    def compute_structure_statistics(self) -> Dict[str, Any]:
        """
        Compute structure statistics.

        Physical Meaning:
            Computes statistical properties of structure formation,
            including mean, variance, and correlation properties.

        Returns:
            Structure statistics
        """
        if not self.evolution_results:
            return {}

        # Use statistical analysis component
        return self.statistical_analysis.compute_structure_statistics()

    def analyze_correlations(self) -> Dict[str, Any]:
        """
        Analyze correlations in structure formation.

        Physical Meaning:
            Analyzes correlations between different structure
            metrics and evolution parameters.

        Returns:
            Correlation analysis
        """
        if not self.evolution_results:
            return {}

        # Use statistical analysis component
        return self.statistical_analysis.analyze_correlations()

    def compare_with_observations(self) -> Dict[str, Any]:
        """
        Compare results with observational data.

        Physical Meaning:
            Compares the theoretical results with observational
            data to validate the model.

        Returns:
            Comparison results
        """
        if not self.observational_data:
            return {}

        # Use observational comparison component
        return self.observational_comparison.compare_with_observations()
