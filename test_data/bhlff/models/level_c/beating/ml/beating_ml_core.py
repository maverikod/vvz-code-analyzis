"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core machine learning beating analysis for Level C.

This module implements the core machine learning-based beating analysis
functionality for analyzing mode beating in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from .beating_ml_patterns import BeatingMLPatterns
from .beating_ml_prediction.beating_ml_prediction_core import (
    BeatingMLPredictionCore as BeatingMLPrediction,
)
from .beating_ml_optimization import BeatingMLOptimization


class BeatingMLCore:
    """
    Core machine learning beating analysis for Level C analysis.

    Physical Meaning:
        Provides core machine learning-based beating analysis functions for analyzing
        mode beating in the 7D phase field, coordinating specialized ML modules.

    Mathematical Foundation:
        Coordinates machine learning techniques for:
        - Pattern classification and recognition
        - Frequency prediction and analysis
        - Coupling prediction and optimization
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize machine learning beating core analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Machine learning parameters
        self.machine_learning_enabled = True
        self.ml_threshold = 1e-8

        # Initialize specialized modules
        self.patterns = BeatingMLPatterns(bvp_core)
        self.prediction = BeatingMLPrediction(bvp_core)
        self.optimization = BeatingMLOptimization(bvp_core)

    def analyze_beating_machine_learning(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze mode beating using machine learning techniques.

        Physical Meaning:
            Analyzes mode beating using machine learning methods
            for advanced pattern recognition and classification.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Machine learning analysis results.
        """
        self.logger.info("Starting machine learning beating analysis")

        # Basic analysis
        basic_results = self._analyze_beating_basic(envelope)

        # Machine learning analysis
        if self.machine_learning_enabled:
            ml_results = self._perform_machine_learning_analysis(
                envelope, basic_results
            )
        else:
            ml_results = {}

        # Combine results
        combined_results = {
            "basic_analysis": basic_results,
            "machine_learning_analysis": ml_results,
        }

        self.logger.info("Machine learning beating analysis completed")
        return combined_results

    def _perform_machine_learning_analysis(
        self, envelope: np.ndarray, basic_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform machine learning analysis on beating data.

        Physical Meaning:
            Performs comprehensive machine learning analysis including
            pattern classification, frequency prediction, and coupling optimization.

        Args:
            envelope (np.ndarray): 7D envelope field data.
            basic_results (Dict[str, Any]): Basic analysis results.

        Returns:
            Dict[str, Any]: Machine learning analysis results.
        """
        ml_results = {}

        # Pattern classification
        if self.patterns.pattern_classification_enabled:
            pattern_results = self.patterns.classify_beating_patterns(envelope)
            ml_results["pattern_classification"] = pattern_results

        # Frequency prediction
        if self.prediction.frequency_prediction_enabled:
            frequency_results = self.prediction.predict_beating_frequencies(envelope)
            ml_results["frequency_prediction"] = frequency_results

        # Coupling prediction
        if self.prediction.coupling_prediction_enabled:
            coupling_results = self.prediction.predict_mode_coupling(envelope)
            ml_results["coupling_prediction"] = coupling_results

        # ML optimization
        if self.optimization.optimization_enabled:
            optimization_results = self.optimization.optimize_ml_parameters(envelope)
            ml_results["ml_optimization"] = optimization_results

        return ml_results

    def _analyze_beating_basic(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Perform basic beating analysis.

        Physical Meaning:
            Performs basic analysis of mode beating patterns
            without machine learning techniques.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Basic analysis results.
        """
        # Basic envelope analysis
        envelope_energy = np.sum(np.abs(envelope) ** 2)
        envelope_max = np.max(np.abs(envelope))
        envelope_mean = np.mean(np.abs(envelope))

        # Basic frequency analysis
        envelope_fft = np.fft.fftn(envelope)
        frequency_spectrum = np.abs(envelope_fft)
        dominant_frequencies = np.argsort(frequency_spectrum.flatten())[-10:]

        return {
            "envelope_energy": envelope_energy,
            "envelope_max": envelope_max,
            "envelope_mean": envelope_mean,
            "dominant_frequencies": dominant_frequencies.tolist(),
            "frequency_spectrum_peak": np.max(frequency_spectrum),
        }
