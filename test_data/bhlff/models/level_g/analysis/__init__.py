"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological analysis tools package for 7D phase field theory.

This package implements analysis tools for cosmological evolution
results, including structure formation analysis, parameter evolution
analysis, and comparison with observational data.

Theoretical Background:
    The cosmological analysis module provides tools for analyzing
    the results of cosmological evolution, including structure
    formation metrics and parameter evolution.

Example:
    >>> from .cosmological_analysis import CosmologicalAnalysis
    >>> analysis = CosmologicalAnalysis(evolution_results)
    >>> structure_analysis = analysis.analyze_structure_formation()
"""

from .cosmological_analysis import CosmologicalAnalysis
from .structure_analysis import StructureAnalysis
from .parameter_analysis import ParameterAnalysis
from .observational_comparison import ObservationalComparisonCore
from .statistical_analysis import StatisticalAnalysis

__all__ = [
    "CosmologicalAnalysis",
    "StructureAnalysis",
    "ParameterAnalysis",
    "ObservationalComparisonCore",
    "StatisticalAnalysis",
]
