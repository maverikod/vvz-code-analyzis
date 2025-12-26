"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis for phase mapping.

This module provides a facade interface for the comprehensive
boundary analysis package, maintaining backward compatibility
while using the full 7D BVP theory implementation.

Theoretical Background:
    Boundary analysis identifies transition points between
    different regimes in parameter space, revealing the
    structure of the phase diagram using 7D BVP theory.

Example:
    >>> analyzer = BoundaryAnalyzer()
    >>> boundaries = analyzer.analyze_regime_boundaries(parameter_grid, classifications)
"""

from .boundary_analysis import BoundaryAnalyzer

# Maintain backward compatibility
__all__ = ["BoundaryAnalyzer"]
