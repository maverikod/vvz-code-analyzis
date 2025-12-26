"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law fitting for BVP framework.

This module provides a facade interface for the comprehensive
power law fitting package, maintaining backward compatibility
while using the full 7D BVP theory implementation.

Theoretical Background:
    Power law fitting involves fitting power law functions
    to data using various optimization methods and statistical
    techniques for 7D phase field theory.

Example:
    >>> fitter = PowerLawFitting(bvp_core)
    >>> results = fitter.fit_power_law(region_data)
"""

from .power_law_fitting import PowerLawFitting

# Maintain backward compatibility: re-export main fitter implementation.
__all__ = ["PowerLawFitting"]
