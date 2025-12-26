"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating ML prediction package.

This package provides comprehensive machine learning prediction functionality
for beating analysis in Level C of 7D phase field theory.

Physical Meaning:
    Provides machine learning-based prediction functions for analyzing
    beating frequencies and mode coupling in the 7D phase field.

Example:
    >>> from .beating_ml_prediction_core import BeatingMLPredictionCore
    >>> predictor = BeatingMLPredictionCore(bvp_core)
    >>> frequencies = predictor.predict_beating_frequencies(envelope)
"""

from .beating_ml_prediction_core import BeatingMLPredictionCore
from .ml_model_manager import MLModelManager
from .feature_extractor import FeatureExtractor
from .prediction_engine import PredictionEngine
from .ml_trainer import MLTrainer

__all__ = [
    "BeatingMLPredictionCore",
    "MLModelManager",
    "FeatureExtractor",
    "PredictionEngine",
    "MLTrainer",
]
