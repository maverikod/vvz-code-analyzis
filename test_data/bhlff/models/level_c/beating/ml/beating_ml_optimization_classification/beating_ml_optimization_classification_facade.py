"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for beating ML optimization classification.

This module provides the main BeatingMLClassificationOptimizer facade class that
coordinates all classification optimization components.
"""

from .beating_ml_optimization_classification_base import BeatingMLClassificationOptimizerBase
from .beating_ml_optimization_classification_optimization import BeatingMLOptimizationClassificationOptimizationMixin
from .beating_ml_optimization_classification_validation import BeatingMLOptimizationClassificationValidationMixin
from .beating_ml_optimization_classification_performance import BeatingMLOptimizationClassificationPerformanceMixin
from .beating_ml_optimization_classification_helpers import BeatingMLOptimizationClassificationHelpersMixin


class BeatingMLClassificationOptimizer(
    BeatingMLClassificationOptimizerBase,
    BeatingMLOptimizationClassificationOptimizationMixin,
    BeatingMLOptimizationClassificationValidationMixin,
    BeatingMLOptimizationClassificationPerformanceMixin,
    BeatingMLOptimizationClassificationHelpersMixin
):
    """
    Facade class for machine learning classification optimizer with all mixins.
    
    Physical Meaning:
        Provides classification parameter optimization functions for improving
        the accuracy and reliability of ML-based beating classification.
        
    Mathematical Foundation:
        Uses optimization techniques to tune classification parameters
        for optimal performance in beating pattern classification.
    """
    pass

