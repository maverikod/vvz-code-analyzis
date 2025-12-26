"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Observational comparison package for cosmological analysis.

This package implements comprehensive observational comparison
functionality for cosmological evolution results using 7D BVP
theory principles.

Theoretical Background:
    Observational comparison in cosmological evolution involves
    comparing theoretical results with observational data to
    validate the model using 7D BVP theory principles.

Example:
    >>> from bhlff.models.level_g.analysis.observational_comparison import ObservationalComparisonCore
    >>> core = ObservationalComparisonCore(evolution_results, observational_data)
    >>> comparison_results = core.compare_with_observations()
"""

from .observational_comparison_core import ObservationalComparisonCore
from .observational_data_loader import ObservationalDataLoader
from .observable_extractor import ObservableExtractor
from .statistical_comparison import StatisticalComparison

__all__ = [
    "ObservationalComparisonCore",
    "ObservationalDataLoader",
    "ObservableExtractor",
    "StatisticalComparison",
]
