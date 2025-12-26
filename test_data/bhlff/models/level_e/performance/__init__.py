"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Performance analysis package for Level E experiments.

This package provides comprehensive performance analysis
functionality for 7D phase field theory simulations.

Theoretical Background:
    Performance analysis provides comprehensive evaluation
    of computational performance, resource usage, and
    optimization opportunities in 7D phase field simulations.

Example:
    >>> from bhlff.models.level_e.performance import PerformanceAnalysis
    >>> analyzer = PerformanceAnalysis(config)
    >>> results = analyzer.analyze_performance()
"""

from .benchmark_tests import BenchmarkTests
from .performance_analyzer import PerformanceAnalyzer
from .profiling import Profiler
from .optimization import Optimizer
from .resource_analysis import ResourceAnalyzer
from .scalability_analysis import ScalabilityAnalyzer
from .performance_analysis import PerformanceAnalysis

__all__ = [
    "BenchmarkTests",
    "PerformanceAnalyzer",
    "Profiler",
    "Optimizer",
    "ResourceAnalyzer",
    "ScalabilityAnalyzer",
    "PerformanceAnalysis",
]
