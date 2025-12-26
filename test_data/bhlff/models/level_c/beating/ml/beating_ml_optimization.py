"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning optimization for beating analysis.

This module implements machine learning parameter optimization functionality
for improving the accuracy and reliability of ML-based beating analysis.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from .beating_ml_optimization_core import BeatingMLOptimizationCore
from .beating_ml_optimization_classification import BeatingMLClassificationOptimizer
from .beating_ml_optimization_prediction import BeatingMLPredictionOptimizer


class BeatingMLOptimization:
    """
    Machine learning optimization for beating analysis.

    Physical Meaning:
        Provides machine learning parameter optimization functions for improving
        the accuracy and reliability of ML-based beating analysis.

    Mathematical Foundation:
        Uses optimization techniques to tune machine learning parameters
        for optimal performance in beating pattern analysis.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize optimization analyzer.

        Physical Meaning:
            Sets up the ML optimization system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Optimization parameters
        self.optimization_enabled = True
        self.optimization_iterations = 100
        self.optimization_tolerance = 1e-6

        # Initialize optimization components
        self._core_optimizer = BeatingMLOptimizationCore(bvp_core)
        self._classification_optimizer = BeatingMLClassificationOptimizer(bvp_core)
        self._prediction_optimizer = BeatingMLPredictionOptimizer(bvp_core)

    def optimize_ml_parameters(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Optimize machine learning parameters.

        Physical Meaning:
            Optimizes machine learning parameters to improve
            accuracy and reliability of beating analysis.

        Mathematical Foundation:
            Uses optimization techniques to tune machine learning parameters
            for optimal performance in beating pattern analysis.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: ML optimization results.
        """
        return self._core_optimizer.optimize_ml_parameters(envelope)

    def optimize_classification_parameters(
        self, envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Optimize classification parameters.

        Physical Meaning:
            Optimizes classification parameters to improve
            accuracy and reliability of beating classification.

        Mathematical Foundation:
            Uses optimization techniques to tune classification parameters
            for optimal performance in beating pattern classification.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Classification optimization results.
        """
        return self._classification_optimizer.optimize_classification_parameters(
            envelope
        )

    def optimize_prediction_parameters(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Optimize prediction parameters.

        Physical Meaning:
            Optimizes prediction parameters to improve
            accuracy and reliability of beating prediction.

        Mathematical Foundation:
            Uses optimization techniques to tune prediction parameters
            for optimal performance in beating pattern prediction.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Prediction optimization results.
        """
        return self._prediction_optimizer.optimize_prediction_parameters(envelope)
