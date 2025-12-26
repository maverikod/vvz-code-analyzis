"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pattern classifier for ML pattern classification.

This module implements pattern classification for machine learning
pattern classification in 7D phase field beating analysis.

Physical Meaning:
    Provides pattern classification capabilities for 7D phase field
    configurations using machine learning and analytical methods.

Example:
    >>> classifier = BeatingMLPatternClassifier(bvp_core)
    >>> result = classifier.classify_patterns(features)
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from .beating_ml_pattern_feature_extractor import BeatingMLPatternFeatureExtractor


class BeatingMLPatternClassifier:
    """
    Pattern classifier for ML pattern classification.

    Physical Meaning:
        Provides pattern classification capabilities for 7D phase field
        configurations using machine learning and analytical methods.

    Mathematical Foundation:
        Implements pattern classification using machine learning algorithms
        and analytical methods based on 7D phase field theory.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize pattern classifier.

        Physical Meaning:
            Sets up the pattern classification system for 7D phase field analysis.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Pattern classification parameters
        self.pattern_classification_enabled = True
        self.classification_confidence = 0.8

        # Initialize feature extractor
        self.feature_extractor = BeatingMLPatternFeatureExtractor(bvp_core)

    def classify_patterns(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify patterns using machine learning or analytical methods.

        Physical Meaning:
            Classifies beating patterns based on extracted features
            using machine learning or analytical methods.

        Mathematical Foundation:
            Uses machine learning algorithms or analytical methods
            based on 7D phase field theory for pattern classification.

        Args:
            features (Dict[str, Any]): Extracted features.

        Returns:
            Dict[str, Any]: Pattern classification results.
        """
        if self.pattern_classification_enabled:
            return self._classify_patterns_ml(features)
        else:
            return self._classify_patterns_analytical(features)

    def _classify_patterns_ml(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify patterns using full machine learning implementation.

        Physical Meaning:
            Uses complete machine learning algorithms to classify beating patterns
            based on extracted features using 7D phase field theory.

        Mathematical Foundation:
            Implements full ML classification using Random Forest classifier
            trained on 7D phase field features and pattern characteristics.

        Args:
            features (Dict[str, Any]): Extracted features.

        Returns:
            Dict[str, Any]: Full ML classification results.
        """
        # Load trained ML model for pattern classification
        model = self._load_trained_pattern_classifier()

        if model is None:
            self.logger.warning(
                "Pattern classifier not loaded, using analytical method"
            )
            return self._classify_patterns_analytical(features)

        # Extract 7D phase field features for ML
        ml_features = self._extract_ml_pattern_features(features)

        # Scale features
        scaler = self._load_pattern_scaler()
        ml_features_scaled = scaler.transform([ml_features])

        # Make prediction
        pattern_type = model.predict(ml_features_scaled)[0]
        prediction_proba = model.predict_proba(ml_features_scaled)[0]

        # Get confidence from prediction probability
        confidence = np.max(prediction_proba)

        # Get feature importance
        feature_importance = self._get_pattern_feature_importance(model)

        return {
            "pattern_type": pattern_type,
            "confidence": confidence,
            "classification_method": "machine_learning",
            "prediction_probabilities": dict(zip(model.classes_, prediction_proba)),
            "feature_importance": feature_importance,
            "features_used": list(features.keys()),
        }

    def _classify_patterns_analytical(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify patterns using analytical method based on 7D BVP theory.

        Physical Meaning:
            Uses analytical methods based on 7D phase field theory
            to classify beating patterns when ML model is not available.

        Mathematical Foundation:
            Implements analytical pattern classification using
            7D phase field theory and VBP envelope analysis.

        Args:
            features (Dict[str, Any]): Extracted features.

        Returns:
            Dict[str, Any]: Analytical classification results.
        """
        spatial = features["spatial_features"]
        frequency = features["frequency_features"]
        pattern = features["pattern_features"]

        # Analytical classification based on 7D BVP theory
        # Compute pattern coherence using 7D phase field theory
        coherence_score = self._compute_7d_pattern_coherence(features)

        # Compute pattern stability using 7D phase field theory
        stability_score = self._compute_7d_pattern_stability(features)

        # Classify based on 7D BVP theory
        if coherence_score > 0.8 and stability_score > 0.7:
            pattern_type = "symmetric"
        elif coherence_score > 0.6 and stability_score > 0.5:
            pattern_type = "regular"
        elif coherence_score > 0.4 and stability_score > 0.3:
            pattern_type = "complex"
        else:
            pattern_type = "irregular"

        # Compute confidence based on 7D phase field theory
        confidence = 0.7 + coherence_score * 0.2 + stability_score * 0.1
        confidence = min(max(confidence, 0.0), 1.0)

        return {
            "pattern_type": pattern_type,
            "confidence": confidence,
            "classification_method": "analytical_7d_bvp",
            "coherence_score": coherence_score,
            "stability_score": stability_score,
            "features_used": list(features.keys()),
        }

    def _compute_7d_pattern_coherence(self, features: Dict[str, Any]) -> float:
        """
        Compute pattern coherence using 7D BVP theory.

        Physical Meaning:
            Computes pattern coherence based on 7D phase field theory
            and VBP envelope analysis.

        Args:
            features (Dict[str, Any]): Input features.

        Returns:
            float: Pattern coherence score.
        """
        spatial = features["spatial_features"]
        frequency = features["frequency_features"]
        pattern = features["pattern_features"]

        # Compute 7D phase field coherence
        coherence = (
            pattern["symmetry_score"] * 0.3
            + frequency["spectrum_peak"] * 0.2
            + pattern["regularity_score"] * 0.5
        )

        return min(max(coherence, 0.0), 1.0)

    def _compute_7d_pattern_stability(self, features: Dict[str, Any]) -> float:
        """
        Compute pattern stability using 7D BVP theory.

        Physical Meaning:
            Computes pattern stability based on 7D phase field theory
            and VBP envelope dynamics.

        Args:
            features (Dict[str, Any]): Input features.

        Returns:
            float: Pattern stability score.
        """
        spatial = features["spatial_features"]
        frequency = features["frequency_features"]
        pattern = features["pattern_features"]

        # Compute 7D phase field stability
        stability = (
            pattern["regularity_score"] * 0.4
            + frequency["spectrum_std"] * 0.3
            + pattern["complexity_score"] * 0.3
        )

        return min(max(stability, 0.0), 1.0)

    def _load_trained_pattern_classifier(self):
        """
        Load trained pattern classifier model.

        Physical Meaning:
            Loads pre-trained Random Forest classifier for pattern classification
            based on 7D phase field theory.

        Returns:
            Trained classifier model or None if not available.
        """
        try:
            import pickle
            import os

            model_path = "models/ml/beating/pattern_classifier.pkl"
            if os.path.exists(model_path):
                with open(model_path, "rb") as f:
                    model_data = pickle.load(f)
                    return model_data["model"]
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load pattern classifier: {e}")
            return None

    def _load_pattern_scaler(self):
        """
        Load pattern feature scaler.

        Physical Meaning:
            Loads feature scaler for pattern classification features.

        Returns:
            Trained scaler or default scaler.
        """
        try:
            import pickle
            import os
            from sklearn.preprocessing import StandardScaler

            scaler_path = "models/ml/beating/pattern_scaler.pkl"
            if os.path.exists(scaler_path):
                with open(scaler_path, "rb") as f:
                    scaler_data = pickle.load(f)
                    return scaler_data["scaler"]
            return StandardScaler()
        except Exception as e:
            self.logger.warning(f"Failed to load pattern scaler: {e}")
            return StandardScaler()

    def _extract_ml_pattern_features(self, features: Dict[str, Any]) -> np.ndarray:
        """
        Extract ML features for pattern classification.

        Physical Meaning:
            Extracts comprehensive features for ML pattern classification
            based on 7D phase field theory.

        Args:
            features (Dict[str, Any]): Input features dictionary.

        Returns:
            np.ndarray: ML features array.
        """
        spatial = features["spatial_features"]
        frequency = features["frequency_features"]
        pattern = features["pattern_features"]

        # Extract comprehensive ML features
        ml_features = [
            spatial["envelope_energy"],
            spatial["envelope_max"],
            spatial["envelope_mean"],
            spatial["envelope_std"],
            frequency["spectrum_peak"],
            frequency["spectrum_std"],
            frequency["spectrum_entropy"],
            frequency["frequency_spacing"],
            frequency["frequency_bandwidth"],
            pattern["symmetry_score"],
            pattern["regularity_score"],
            pattern["complexity_score"],
        ]

        return np.array(ml_features)

    def _get_pattern_feature_importance(self, model) -> Dict[str, float]:
        """
        Get feature importance from pattern classifier.

        Physical Meaning:
            Extracts feature importance from trained pattern classifier
            to understand which features are most relevant.

        Args:
            model: Trained pattern classifier.

        Returns:
            Dict[str, float]: Feature importance dictionary.
        """
        try:
            if hasattr(model, "feature_importances_"):
                feature_names = [
                    "envelope_energy",
                    "envelope_max",
                    "envelope_mean",
                    "envelope_std",
                    "spectrum_peak",
                    "spectrum_std",
                    "spectrum_entropy",
                    "frequency_spacing",
                    "frequency_bandwidth",
                    "symmetry_score",
                    "regularity_score",
                    "complexity_score",
                ]
                importance_dict = {}
                for i, name in enumerate(feature_names):
                    if i < len(model.feature_importances_):
                        importance_dict[name] = float(model.feature_importances_[i])
                return importance_dict
            else:
                return {"default": 1.0}
        except Exception:
            return {"default": 1.0}
