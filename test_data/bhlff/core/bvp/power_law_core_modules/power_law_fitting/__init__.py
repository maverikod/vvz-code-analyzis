"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law fitting package for BVP framework.

This package implements comprehensive power law fitting
functionality for 7D BVP theory applications.

Theoretical Background:
    Power law fitting involves fitting power law functions
    to data using various optimization methods and statistical
    techniques for 7D phase field theory.

Example:
    >>> from bhlff.core.bvp.power_law_core_modules.power_law_fitting import PowerLawFitting
    >>> fitter = PowerLawFitting(bvp_core)
    >>> results = fitter.fit_power_law(region_data)
"""

from .power_law_fitting import PowerLawFitting
from .advanced_fitting import AdvancedPowerLawFitting
from .quality_analysis import QualityAnalyzer
from .optimization_methods import OptimizationMethods

__all__ = [
    "PowerLawFitting",
    "AdvancedPowerLawFitting",
    "QualityAnalyzer",
    "OptimizationMethods",
]
