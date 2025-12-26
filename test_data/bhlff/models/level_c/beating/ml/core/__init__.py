"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core ML prediction modules for beating analysis.

This package contains core machine learning prediction functionality
for beating analysis in Level C of 7D phase field theory.
"""

from .ml_models import MLModelManager
from .feature_extraction import FeatureExtractor
from .prediction_engine import PredictionEngine
from .feature_calculators import FeatureCalculator
from .phase_field_features import PhaseFieldFeatures
from .bvp_7d_analytics import BVP7DAnalytics
from .training_data_generator import TrainingDataGenerator
from .ml_trainer import MLTrainer

__all__ = [
    "MLModelManager",
    "FeatureExtractor",
    "PredictionEngine",
    "FeatureCalculator",
    "PhaseFieldFeatures",
    "BVP7DAnalytics",
    "TrainingDataGenerator",
    "MLTrainer",
]
