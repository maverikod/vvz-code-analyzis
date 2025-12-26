"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scaling analysis package for performance optimization.

This package provides comprehensive scaling analysis functionality
for analyzing computational scaling behavior in 7D phase field
theory simulations.

Theoretical Background:
    Scaling analysis investigates the relationship between
    computational cost and problem size, providing insights
    into algorithmic efficiency and optimization opportunities.

Example:
    >>> from bhlff.models.level_e.performance.scaling import ScalingAnalyzer
    >>> analyzer = ScalingAnalyzer(config)
    >>> results = analyzer.analyze_scaling_behavior()
"""

from .base_scaling import BaseScalingAnalyzer
from .performance_scaling import PerformanceScalingAnalyzer
from .optimization_scaling import OptimizationScalingAnalyzer
from typing import Dict, Any
import numpy as np


class ScalingAnalyzer:
    """
    Comprehensive scaling analysis for computational efficiency.

    Physical Meaning:
        Analyzes the relationship between computational cost and
        problem size in the 7D phase field simulations, providing
        optimization recommendations.

    Mathematical Foundation:
        Implements comprehensive scaling analysis:
        - Base scaling: fundamental scaling behavior analysis
        - Performance scaling: performance-resource relationships
        - Optimization scaling: optimization opportunity identification
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize comprehensive scaling analyzer.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.base_analyzer = BaseScalingAnalyzer(config)
        self.performance_analyzer = PerformanceScalingAnalyzer(config)
        self.optimization_analyzer = OptimizationScalingAnalyzer(config)

    def analyze_scaling_behavior(self) -> Dict[str, Any]:
        """Analyze comprehensive scaling behavior."""
        # Base scaling analysis
        base_results = self.base_analyzer.analyze_base_scaling()

        # Performance scaling analysis
        performance_results = self.performance_analyzer.analyze_performance_scaling()

        # Optimization scaling analysis
        optimization_results = self.optimization_analyzer.analyze_optimization_scaling()

        # Combine results
        comprehensive_results = {
            "base_scaling": base_results,
            "performance_scaling": performance_results,
            "optimization_scaling": optimization_results,
            "summary": self._create_scaling_summary(
                base_results, performance_results, optimization_results
            ),
        }

        return comprehensive_results

    def _create_scaling_summary(
        self,
        base_results: Dict[str, Any],
        performance_results: Dict[str, Any],
        optimization_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create comprehensive scaling summary."""
        # Extract key metrics
        grid_scaling = base_results.get("grid_scaling", {})
        cpu_scaling = performance_results.get("cpu_scaling", {})
        overall_optimization = optimization_results.get("overall_optimization", {})

        # Compute overall scaling grade
        scaling_exponents = [
            grid_scaling.get("scaling_exponent", 1.0),
            cpu_scaling.get("cpu_scaling_exponent", 1.0),
        ]
        avg_scaling_exponent = np.mean(scaling_exponents)

        # Determine scaling grade
        if avg_scaling_exponent < 1.5:
            scaling_grade = "A"
        elif avg_scaling_exponent < 2.0:
            scaling_grade = "B"
        elif avg_scaling_exponent < 3.0:
            scaling_grade = "C"
        else:
            scaling_grade = "D"

        return {
            "scaling_grade": scaling_grade,
            "avg_scaling_exponent": float(avg_scaling_exponent),
            "optimization_potential": overall_optimization.get(
                "overall_potential", 0.0
            ),
            "priority_optimizations": overall_optimization.get(
                "priority_optimizations", []
            ),
            "analysis_complete": True,
        }
