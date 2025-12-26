"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning prediction for beating analysis.

This module implements machine learning-based prediction functionality
for analyzing beating frequencies and mode coupling in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from .beating_ml_prediction_core import BeatingMLPredictionCore
from .beating_ml_prediction_features import BeatingMLPredictionFeatures


class BeatingMLPrediction:
    """
    Machine learning prediction for beating analysis.

    Physical Meaning:
        Provides machine learning-based prediction functions for analyzing
        beating frequencies and mode coupling in the 7D phase field.

    Mathematical Foundation:
        Uses machine learning techniques for frequency prediction and
        mode coupling analysis in beating phenomena.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize prediction analyzer.

        Physical Meaning:
            Sets up the ML prediction system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Prediction parameters
        self.frequency_prediction_enabled = True
        self.coupling_prediction_enabled = True
        self.prediction_confidence = 0.7

        # Initialize prediction components
        self._core_predictor = BeatingMLPredictionCore(bvp_core)
        self._feature_extractor = BeatingMLPredictionFeatures(bvp_core)

    def predict_beating_frequencies(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict beating frequencies using machine learning.

        Physical Meaning:
            Predicts beating frequencies using machine learning
            techniques for 7D phase field analysis.

        Mathematical Foundation:
            Uses machine learning techniques for frequency prediction
            in beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency prediction results.
        """
        return self._core_predictor.predict_beating_frequencies(envelope)

    def predict_mode_coupling(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict mode coupling using machine learning.

        Physical Meaning:
            Predicts mode coupling using machine learning
            techniques for 7D phase field analysis.

        Mathematical Foundation:
            Uses machine learning techniques for mode coupling
            analysis in beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Mode coupling prediction results.
        """
        return self._core_predictor.predict_mode_coupling(envelope)
