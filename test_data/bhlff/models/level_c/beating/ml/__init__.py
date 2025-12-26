"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning beating analysis modules for Level C.

This package provides machine learning-based beating analysis functionality
for analyzing mode beating in the 7D phase field.
"""

from .beating_ml_core import BeatingMLCore
from .beating_ml_patterns import BeatingMLPatterns
from .beating_ml_prediction.beating_ml_prediction_core import (
    BeatingMLPredictionCore as BeatingMLPrediction,
)
from .beating_ml_optimization import BeatingMLOptimization

__all__ = [
    "BeatingMLCore",
    "BeatingMLPatterns",
    "BeatingMLPrediction",
    "BeatingMLOptimization",
]
