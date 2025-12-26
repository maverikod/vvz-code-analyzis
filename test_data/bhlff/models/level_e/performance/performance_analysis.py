"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Performance analysis for Level E experiments.

This module implements performance analysis functionality
for analyzing computational performance and resource usage
in 7D phase field theory simulations.

Theoretical Background:
    Performance analysis provides comprehensive evaluation
    of computational performance, resource usage, and
    optimization opportunities in 7D phase field simulations.

Example:
    >>> analyzer = PerformanceAnalysis(config)
    >>> results = analyzer.analyze_performance()
"""

import numpy as np
import time
import psutil
from typing import Dict, Any, List, Optional, Tuple

from bhlff.models.level_e.performance.benchmark_tests import BenchmarkTests
from bhlff.models.level_e.performance.profiling import Profiler
from bhlff.models.level_e.performance.optimization import Optimizer
from bhlff.models.level_e.performance.resource_analysis import ResourceAnalyzer
from bhlff.models.level_e.performance.scalability_analysis import ScalabilityAnalyzer


class PerformanceAnalysis:
    """
    Performance analysis for Level E experiments.

    Physical Meaning:
        Analyzes computational performance and resource usage
        in 7D phase field theory simulations, providing insights
        into optimization opportunities and bottlenecks.

    Mathematical Foundation:
        Implements performance analysis through:
        - Execution time profiling: T(n) = O(n^α)
        - Memory usage analysis: M(n) = O(n^β)
        - Scalability assessment: S(n) = T(n)/T(1)
        - Efficiency metrics: E(n) = S(n)/n
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize performance analysis.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._setup_performance_modules()

    def _setup_performance_modules(self) -> None:
        """Setup performance analysis modules."""
        self.benchmark_tests = BenchmarkTests(self.config)
        # Lazy import to avoid circular dependency with performance_analyzer
        from bhlff.models.level_e.performance.performance_analyzer import (
            PerformanceAnalyzer,
        )

        self.performance_analyzer = PerformanceAnalyzer(self.config)
        self.profiler = Profiler(self.config)
        self.optimizer = Optimizer(self.config)
        self.resource_analyzer = ResourceAnalyzer(self.config)
        self.scalability_analyzer = ScalabilityAnalyzer(self.config)

    def analyze_performance(self) -> Dict[str, Any]:
        """Analyze computational performance."""
        performance_results = {}

        # Run benchmark tests
        benchmark_results = self.benchmark_tests.run_benchmark_tests()

        # Analyze performance
        performance_analysis = self.performance_analyzer.analyze_performance()

        # Profile simulation
        profiling_results = self.profiler.profile_simulation()

        # Optimize performance
        optimization_results = self.optimizer.optimize_performance()

        # Analyze resources
        resource_analysis = self.resource_analyzer.analyze_resources()

        # Analyze scalability
        scalability_analysis = self.scalability_analyzer.analyze_scalability()

        performance_results.update(
            {
                "benchmark_results": benchmark_results,
                "performance_analysis": performance_analysis,
                "profiling_results": profiling_results,
                "optimization_results": optimization_results,
                "resource_analysis": resource_analysis,
                "scalability_analysis": scalability_analysis,
            }
        )

        return performance_results

    def _analyze_execution_time(self) -> Dict[str, Any]:
        """Analyze execution time performance."""
        return self.performance_analyzer._analyze_execution_time()

    def _analyze_memory_usage(self) -> Dict[str, Any]:
        """Analyze memory usage performance."""
        return self.performance_analyzer._analyze_memory_usage()

    def _analyze_scalability(self) -> Dict[str, Any]:
        """Analyze computational scalability."""
        return self.performance_analyzer._analyze_scalability()

    def _analyze_efficiency(self) -> Dict[str, Any]:
        """Analyze computational efficiency."""
        return self.performance_analyzer._analyze_efficiency()
