"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for beating ML optimization core.

This module provides the main BeatingMLOptimizationCore facade class that
coordinates all beating ML optimization core components.
"""

from .beating_ml_optimization_core_base import BeatingMLOptimizationCoreBase
from .beating_ml_optimization_core_optimization import BeatingMLOptimizationCoreOptimizationMixin
from .beating_ml_optimization_core_validation import BeatingMLOptimizationCoreValidationMixin
from .beating_ml_optimization_core_performance import BeatingMLOptimizationCorePerformanceMixin


class BeatingMLOptimizationCore(
    BeatingMLOptimizationCoreBase,
    BeatingMLOptimizationCoreOptimizationMixin,
    BeatingMLOptimizationCoreValidationMixin,
    BeatingMLOptimizationCorePerformanceMixin
):
    """
    Facade class for beating ML optimization core with all mixins.
    
    Physical Meaning:
        Provides core machine learning parameter optimization functions for improving
        the accuracy and reliability of ML-based beating analysis.
    """
    pass

