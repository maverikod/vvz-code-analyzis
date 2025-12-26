"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core beating ML prediction functionality.

This module implements core ML prediction functionality for beating analysis
in Level C of 7D phase field theory.

Physical Meaning:
    Provides core machine learning-based prediction functions for analyzing
    beating frequencies and mode coupling in the 7D phase field.

Example:
    >>> predictor = BeatingMLPredictionCore(bvp_core)
    >>> frequencies = predictor.predict_beating_frequencies(envelope)
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from bhlff.core.bvp.bvp_core.bvp_vectorized_processor import BVPVectorizedProcessor
from bhlff.core.domain.vectorized_block_processor import VectorizedBlockProcessor
from .ml_model_manager import MLModelManager
from .feature_extractor import FeatureExtractor
from .prediction_engine import PredictionEngine
from .ml_trainer import MLTrainer
from .beating_ml_prediction_helpers import BeatingMLPredictionHelpers
from .beating_ml_prediction_analytical import BeatingMLPredictionAnalytical


class BeatingMLPredictionCore:
    """
    Core machine learning prediction for beating analysis.

    Physical Meaning:
        Provides core machine learning-based prediction functions for analyzing
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

        # Initialize core components
        self.model_manager = MLModelManager()
        self.feature_extractor = FeatureExtractor()
        self.prediction_engine = PredictionEngine(
            self.model_manager, self.feature_extractor
        )
        self.ml_trainer = MLTrainer(self.model_manager)
        
        # Initialize helper classes
        self.helpers = BeatingMLPredictionHelpers(self.model_manager)
        self.analytical = BeatingMLPredictionAnalytical(self.feature_extractor)

        # Initialize vectorized processor for ML prediction
        self._setup_vectorized_processor()

    def predict_beating_frequencies(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict beating frequencies using full ML implementation.

        Physical Meaning:
            Predicts beating frequencies using complete machine learning
            implementation based on 7D phase field theory and VBP envelope analysis.

        Mathematical Foundation:
            Uses full Random Forest regression trained on 7D phase field
            data to predict beating frequencies from spectral features.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Full ML frequency prediction results.
        """
        self.logger.info("Starting full ML frequency prediction")

        # Extract 7D phase field features
        features = self.feature_extractor.extract_frequency_features(envelope)
        phase_features = self.feature_extractor.extract_7d_phase_features(features)

        # Load trained ML model
        model = self.helpers.load_trained_frequency_model()
        scaler = self.helpers.load_frequency_scaler()

        if model is not None and scaler is not None:
            # Scale features
            phase_features_scaled = scaler.transform([phase_features])

            # Make prediction using trained model
            predicted_frequencies = model.predict(phase_features_scaled)[0]

            # Get prediction confidence
            prediction_confidence = self.helpers.compute_prediction_confidence(
                phase_features_scaled, model
            )

            # Get feature importance
            feature_importance = self.helpers.get_feature_importance(model)

            prediction_results = {
                "predicted_frequencies": predicted_frequencies.tolist(),
                "prediction_confidence": prediction_confidence,
                "feature_importance": feature_importance,
                "model_type": "RandomForest",
                "prediction_variance": self.helpers.compute_prediction_variance(
                    phase_features_scaled, model
                ),
                "prediction_method": "full_ml",
            }
        else:
            # Use full analytical method as fallback
            prediction_results = self.analytical.predict_frequencies_analytical(features)

        self.logger.info("Full ML frequency prediction completed")
        return prediction_results

    def predict_mode_coupling(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict mode coupling using full ML implementation.

        Physical Meaning:
            Predicts mode coupling using complete machine learning
            implementation based on 7D phase field theory and VBP envelope interactions.

        Mathematical Foundation:
            Uses full Neural Network regression trained on 7D phase field
            data to predict mode coupling from interaction features.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Full ML coupling prediction results.
        """
        self.logger.info("Starting full ML coupling prediction")

        # Extract 7D phase field features
        features = self.feature_extractor.extract_coupling_features(envelope)
        phase_features = self.feature_extractor.extract_7d_phase_features(features)

        # Load trained ML model
        model = self.helpers.load_trained_coupling_model()
        scaler = self.helpers.load_coupling_scaler()

        if model is not None and scaler is not None:
            # Scale features
            phase_features_scaled = scaler.transform([phase_features])

            # Make prediction using trained model
            predicted_coupling_raw = model.predict(phase_features_scaled)[0]

            # Format prediction results
            predicted_coupling = {
                "coupling_strength": predicted_coupling_raw[0],
                "interaction_energy": predicted_coupling_raw[1],
                "coupling_symmetry": predicted_coupling_raw[2],
                "nonlinear_strength": predicted_coupling_raw[3],
                "mixing_degree": predicted_coupling_raw[4],
                "coupling_efficiency": predicted_coupling_raw[5],
            }

            # Get prediction confidence
            prediction_confidence = self.helpers.compute_prediction_confidence(
                phase_features_scaled, model
            )

            # Get feature importance
            feature_importance = self.helpers.get_feature_importance(model)

            prediction_results = {
                "predicted_coupling": predicted_coupling,
                "prediction_confidence": prediction_confidence,
                "feature_importance": feature_importance,
                "model_type": "NeuralNetwork",
                "prediction_variance": self.helpers.compute_prediction_variance(
                    phase_features_scaled, model
                ),
                "prediction_method": "full_ml",
            }
        else:
            # Use full analytical method as fallback
            prediction_results = self.analytical.predict_coupling_analytical(features)

        self.logger.info("Full ML coupling prediction completed")
        return prediction_results

    def train_frequency_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train frequency prediction model using 7D BVP theory.

        Physical Meaning:
            Trains Random Forest model for frequency prediction using
            7D phase field theory and VBP envelope configurations.

        Mathematical Foundation:
            Uses Random Forest regression trained on synthetic 7D phase field
            data to predict beating frequencies from spectral features.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results and model performance.
        """
        self.logger.info(f"Training frequency model with {n_samples} samples")
        return self.ml_trainer.train_frequency_model(n_samples)

    def train_coupling_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train coupling prediction model using 7D BVP theory.

        Physical Meaning:
            Trains Neural Network model for coupling prediction using
            7D phase field theory and VBP envelope interactions.

        Mathematical Foundation:
            Uses Neural Network regression trained on synthetic 7D phase field
            data to predict mode coupling from interaction features.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results and model performance.
        """
        self.logger.info(f"Training coupling model with {n_samples} samples")
        return self.ml_trainer.train_coupling_model(n_samples)

    def train_all_models(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train all ML models using 7D BVP theory.

        Physical Meaning:
            Trains both frequency and coupling prediction models using
            7D phase field theory and VBP envelope configurations.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results for all models.
        """
        self.logger.info(f"Training all models with {n_samples} samples")
        return self.ml_trainer.train_all_models(n_samples)

    def validate_models(self, n_samples: int = 200) -> Dict[str, Any]:
        """
        Validate trained ML models.

        Physical Meaning:
            Validates trained ML models using independent test data
            to ensure prediction accuracy and reliability.

        Args:
            n_samples (int): Number of validation samples to generate.

        Returns:
            Dict[str, Any]: Validation results for all models.
        """
        self.logger.info(f"Validating models with {n_samples} samples")
        return self.ml_trainer.validate_models(n_samples)

    def get_model_performance(self) -> Dict[str, Any]:
        """
        Get model performance metrics.

        Physical Meaning:
            Returns performance metrics for trained ML models
            to assess prediction quality and reliability.

        Returns:
            Dict[str, Any]: Model performance metrics.
        """
        return self.ml_trainer.get_model_performance()

    def _setup_vectorized_processor(self) -> None:
        """Setup vectorized processor for ML prediction."""
        if self.bvp_core is None:
            self.logger.warning(
                "BVP core not available, skipping vectorized processor initialization"
            )
            self.vectorized_processor = None
            self.vectorized_block_processor = None
            return

        try:
            # Get domain and config from BVP core
            domain = self.bvp_core.domain
            config = self.bvp_core.config

            # Initialize vectorized BVP processor
            self.vectorized_processor = BVPVectorizedProcessor(
                domain=domain, config=config, block_size=8, overlap=2, use_cuda=True
            )

            # Initialize vectorized block processor for ML operations
            self.vectorized_block_processor = VectorizedBlockProcessor(
                domain=domain, block_size=16, overlap=4, use_cuda=True
            )

            self.logger.info("Vectorized processor initialized for ML prediction")

        except Exception as e:
            self.logger.warning(f"Failed to initialize vectorized processor: {e}")
            self.vectorized_processor = None
            self.vectorized_block_processor = None
