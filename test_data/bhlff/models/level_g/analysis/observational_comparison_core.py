"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core observational comparison methods for cosmological analysis in 7D phase field theory.

This module provides a facade interface for the comprehensive
observational comparison package, maintaining backward compatibility
while using the full 7D BVP theory implementation.

Theoretical Background:
    Observational comparison in cosmological evolution involves
    comparing theoretical results with observational data to
    validate the model using 7D BVP theory principles.

Example:
    >>> core = ObservationalComparisonCore(evolution_results, observational_data)
    >>> comparison_results = core.compare_with_observations()
"""

from .observational_comparison import ObservationalComparisonCore

# Maintain backward compatibility
__all__ = ["ObservationalComparisonCore"]
