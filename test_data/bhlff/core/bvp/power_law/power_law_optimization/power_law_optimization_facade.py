"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for power law optimization.

This module provides the main PowerLawOptimization facade class that
coordinates all power law optimization components.
"""

from .power_law_optimization_base import PowerLawOptimizationBase
from .power_law_optimization_region import PowerLawOptimizationRegionMixin
from .power_law_optimization_quality import PowerLawOptimizationQualityMixin
from .power_law_optimization_regions import PowerLawOptimizationRegionsMixin
from .power_law_optimization_helpers import PowerLawOptimizationHelpersMixin


class PowerLawOptimization(
    PowerLawOptimizationBase,
    PowerLawOptimizationRegionMixin,
    PowerLawOptimizationQualityMixin,
    PowerLawOptimizationRegionsMixin,
    PowerLawOptimizationHelpersMixin
):
    """
    Facade class for power law optimization analyzer with all mixins.
    
    Physical Meaning:
        Provides optimization of power law fits for better accuracy
        and reliability using 7D phase field theory principles.
    """
    pass

