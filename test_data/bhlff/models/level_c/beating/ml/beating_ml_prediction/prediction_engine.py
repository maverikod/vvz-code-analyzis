"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Prediction engine functionality.

This module implements prediction engine for ML-based prediction including
model inference, confidence estimation, and uncertainty quantification.

Physical Meaning:
    Provides prediction engine for machine learning-based prediction
    of beating frequencies and mode coupling in 7D phase field theory.

Example:
    >>> engine = PredictionEngine(model_manager, feature_extractor)
    >>> prediction = engine.predict_frequencies(envelope)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging


class PredictionEngine:
    """
    Prediction engine for ML-based prediction.

    Physical Meaning:
        Provides prediction engine for machine learning-based prediction
        of beating frequencies and mode coupling in 7D phase field theory.

    Mathematical Foundation:
        Implements model inference, confidence estimation, and uncertainty
        quantification for ML-based prediction analysis.
    """

    def __init__(self, model_manager, feature_extractor):
        """
        Initialize prediction engine.

        Args:
            model_manager: ML model manager instance.
            feature_extractor: Feature extractor instance.
        """
        self.model_manager = model_manager
        self.feature_extractor = feature_extractor
        self.logger = logging.getLogger(__name__)

    def predict_frequencies(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict beating frequencies using ML models.

        Physical Meaning:
            Predicts beating frequencies using trained ML models
            based on 7D phase field theory and spectral analysis.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency prediction results.
        """
        try:
            # Extract features
            features = self.feature_extractor.extract_frequency_features(envelope)
            phase_features = self.feature_extractor.extract_7d_phase_features(features)

            # Load model and scaler
            model = self.model_manager.get_frequency_model()
            scaler = self.model_manager.get_frequency_scaler()

            if model is not None and scaler is not None:
                # Scale features
                phase_features_scaled = scaler.transform([phase_features])

                # Make prediction
                predicted_frequencies = model.predict(phase_features_scaled)[0]

                # Compute confidence and uncertainty
                confidence = self._compute_prediction_confidence(
                    phase_features_scaled, model
                )
                uncertainty = self._compute_prediction_uncertainty(
                    phase_features_scaled, model
                )

                return {
                    "predicted_frequencies": predicted_frequencies.tolist(),
                    "prediction_confidence": confidence,
                    "prediction_uncertainty": uncertainty,
                    "model_type": "RandomForest",
                    "prediction_method": "ml",
                }
            else:
                # Fallback to analytical prediction
                return self._predict_frequencies_analytical(features)

        except Exception as e:
            self.logger.error(f"Frequency prediction failed: {e}")
            return {
                "predicted_frequencies": [0.0, 0.0, 0.0],
                "prediction_confidence": 0.0,
            }

    def predict_coupling(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Predict mode coupling using ML models.

        Physical Meaning:
            Predicts mode coupling using trained ML models
            based on 7D phase field theory and interaction analysis.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Coupling prediction results.
        """
        try:
            # Extract features
            features = self.feature_extractor.extract_coupling_features(envelope)
            phase_features = self.feature_extractor.extract_7d_phase_features(features)

            # Load model and scaler
            model = self.model_manager.get_coupling_model()
            scaler = self.model_manager.get_coupling_scaler()

            if model is not None and scaler is not None:
                # Scale features
                phase_features_scaled = scaler.transform([phase_features])

                # Make prediction
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

                # Compute confidence and uncertainty
                confidence = self._compute_prediction_confidence(
                    phase_features_scaled, model
                )
                uncertainty = self._compute_prediction_uncertainty(
                    phase_features_scaled, model
                )

                return {
                    "predicted_coupling": predicted_coupling,
                    "prediction_confidence": confidence,
                    "prediction_uncertainty": uncertainty,
                    "model_type": "NeuralNetwork",
                    "prediction_method": "ml",
                }
            else:
                # Fallback to analytical prediction
                return self._predict_coupling_analytical(features)

        except Exception as e:
            self.logger.error(f"Coupling prediction failed: {e}")
            return {"predicted_coupling": {}, "prediction_confidence": 0.0}

    def _compute_prediction_confidence(self, features: np.ndarray, model) -> float:
        """Compute prediction confidence from ML model."""
        try:
            if hasattr(model, "predict_proba"):
                # For models with probability output
                proba = model.predict_proba(features)
                confidence = np.max(proba)
            else:
                # For regression models, use prediction variance
                predictions = []
                if hasattr(model, "estimators_"):  # Random Forest
                    for estimator in model.estimators_:
                        predictions.append(estimator.predict(features))
                    variance = np.var(predictions)
                    confidence = 1.0 / (1.0 + variance)
                else:
                    # Default confidence based on 7D phase field analysis
                    confidence = 0.8
            return min(max(confidence, 0.0), 1.0)
        except Exception:
            return 0.7  # Default confidence

    def _compute_prediction_uncertainty(self, features: np.ndarray, model) -> float:
        """Compute prediction uncertainty from ML model."""
        try:
            if hasattr(model, "estimators_"):  # Random Forest
                predictions = []
                for estimator in model.estimators_:
                    predictions.append(estimator.predict(features))
                uncertainty = np.std(predictions)
                return float(uncertainty)
            else:
                # For single models, return default uncertainty
                return 0.1
        except Exception:
            return 0.1

    def _predict_frequencies_analytical(
        self, features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Predict frequencies using analytical method."""
        try:
            # Extract features
            spectral_entropy = features.get("spectral_entropy", 0.0)
            frequency_spacing = features.get("frequency_spacing", 0.0)
            frequency_bandwidth = features.get("frequency_bandwidth", 0.0)
            phase_coherence = features.get("phase_coherence", 0.0)

            # Compute analytical frequency prediction
            predicted_frequencies = [
                spectral_entropy * 100.0,
                frequency_spacing * 50.0,
                frequency_bandwidth * 25.0,
            ]

            # Compute prediction confidence based on phase coherence
            prediction_confidence = min(1.0, phase_coherence + 0.3)

            return {
                "predicted_frequencies": predicted_frequencies,
                "prediction_confidence": prediction_confidence,
                "prediction_method": "analytical",
            }

        except Exception as e:
            self.logger.error(f"Analytical frequency prediction failed: {e}")
            return {
                "predicted_frequencies": [0.0, 0.0, 0.0],
                "prediction_confidence": 0.0,
            }

    def _predict_coupling_analytical(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict coupling using analytical method."""
        try:
            # Extract features
            coupling_strength = features.get("coupling_strength", 0.0)
            interaction_energy = features.get("interaction_energy", 0.0)
            coupling_symmetry = features.get("coupling_symmetry", 0.0)
            nonlinear_strength = features.get("nonlinear_strength", 0.0)
            mixing_degree = features.get("mixing_degree", 0.0)
            coupling_efficiency = features.get("coupling_efficiency", 0.0)
            phase_coherence = features.get("phase_coherence", 0.0)

            # Compute analytical coupling prediction
            predicted_coupling = {
                "coupling_strength": coupling_strength * 1.2,
                "interaction_energy": interaction_energy * 0.8,
                "coupling_symmetry": coupling_symmetry * 1.1,
                "nonlinear_strength": nonlinear_strength * 0.9,
                "mixing_degree": mixing_degree * 1.0,
                "coupling_efficiency": coupling_efficiency * 1.05,
            }

            # Compute prediction confidence based on interaction strength
            prediction_confidence = min(1.0, coupling_strength + phase_coherence * 0.5)

            return {
                "predicted_coupling": predicted_coupling,
                "prediction_confidence": prediction_confidence,
                "prediction_method": "analytical",
            }

        except Exception as e:
            self.logger.error(f"Analytical coupling prediction failed: {e}")
            return {"predicted_coupling": {}, "prediction_confidence": 0.0}
