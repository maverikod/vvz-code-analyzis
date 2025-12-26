"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Performance analysis facade for Level E experiments.

This module provides a facade interface for performance analysis,
delegating to specialized modules for different aspects of performance
monitoring and optimization.

Theoretical Background:
    Performance analysis investigates the relationship between computational
    cost and accuracy in the 7D phase field simulations. This is crucial
    for practical applications where computational resources are limited.

Mathematical Foundation:
    Analyzes scaling behavior: T(N) ~ N^α where T is computation time
    and N is problem size. Optimizes accuracy vs cost trade-offs.

Example:
    >>> analyzer = PerformanceAnalyzer(config)
    >>> results = analyzer.analyze_performance()
"""

from .performance.performance_analyzer import PerformanceAnalyzer

# Re-export the main class for backward compatibility
__all__ = ["PerformanceAnalyzer"]
