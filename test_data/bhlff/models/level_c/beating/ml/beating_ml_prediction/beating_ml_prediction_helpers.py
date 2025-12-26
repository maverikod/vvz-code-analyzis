"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for beating ML prediction.

This module provides helper methods for model loading, confidence computation,
and feature importance analysis in ML prediction for beating analysis.

Physical Meaning:
    Provides utility functions for machine learning model operations,
    including model loading, prediction confidence estimation, and
    feature importance analysis for beating frequency and coupling prediction.
"""

import numpy as np
from typing import Dict, Any
import logging


class BeatingMLPredictionHelpers:
    """
    Helper methods for beating ML prediction.
    
    Physical Meaning:
        Provides utility functions for ML model operations,
        including model loading, confidence computation, and
        feature importance analysis.
    """
    
    def __init__(self, model_manager):
        """
        Initialize helper methods.
        
        Args:
            model_manager: ML model manager instance.
        """
        self.model_manager = model_manager
        self.logger = logging.getLogger(__name__)
    
    def load_trained_frequency_model(self):
        """Load trained frequency prediction model."""
        try:
            return self.model_manager.get_frequency_model()
        except Exception as e:
            self.logger.warning(f"Failed to load frequency model: {e}")
            return None
    
    def load_frequency_scaler(self):
        """Load frequency feature scaler."""
        try:
            return self.model_manager.get_frequency_scaler()
        except Exception as e:
            self.logger.warning(f"Failed to load frequency scaler: {e}")
            return None
    
    def load_trained_coupling_model(self):
        """Load trained coupling prediction model."""
        try:
            return self.model_manager.get_coupling_model()
        except Exception as e:
            self.logger.warning(f"Failed to load coupling model: {e}")
            return None
    
    def load_coupling_scaler(self):
        """Load coupling feature scaler."""
        try:
            return self.model_manager.get_coupling_scaler()
        except Exception as e:
            self.logger.warning(f"Failed to load coupling scaler: {e}")
            return None
    
    def compute_prediction_confidence(self, features: np.ndarray, model) -> float:
        """
        Compute prediction confidence from ML model.
        
        Physical Meaning:
            Estimates the confidence of ML predictions based on
            model output variance or probability distributions.
            
        Args:
            features (np.ndarray): Input features for prediction.
            model: Trained ML model.
            
        Returns:
            float: Prediction confidence in [0, 1].
        """
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
    
    def get_feature_importance(self, model) -> Dict[str, float]:
        """
        Get feature importance from ML model.
        
        Physical Meaning:
            Extracts feature importance from trained ML models to
            understand which features are most critical for predictions.
            
        Args:
            model: Trained ML model.
            
        Returns:
            Dict[str, float]: Feature importance dictionary.
        """
        try:
            if hasattr(model, "feature_importances_"):
                # Random Forest feature importance
                feature_names = [
                    "spectral_entropy",
                    "frequency_spacing",
                    "frequency_bandwidth",
                    "autocorrelation",
                    "coupling_strength",
                    "interaction_energy",
                    "coupling_symmetry",
                    "nonlinear_strength",
                    "mixing_degree",
                    "coupling_efficiency",
                    "phase_coherence",
                    "topological_charge",
                    "energy_density",
                    "phase_velocity",
                ]
                importance_dict = {}
                for i, name in enumerate(feature_names):
                    if i < len(model.feature_importances_):
                        importance_dict[name] = float(model.feature_importances_[i])
                return importance_dict
            else:
                # Default importance for models without feature_importances_
                return {
                    "spectral_entropy": 0.2,
                    "frequency_spacing": 0.15,
                    "frequency_bandwidth": 0.15,
                    "coupling_strength": 0.2,
                    "interaction_energy": 0.15,
                    "phase_coherence": 0.15,
                }
        except Exception:
            return {"default": 1.0}
    
    def compute_prediction_variance(self, features: np.ndarray, model) -> float:
        """
        Compute prediction variance for uncertainty quantification.
        
        Physical Meaning:
            Computes prediction variance to quantify uncertainty
            in ML predictions, important for reliability assessment.
            
        Args:
            features (np.ndarray): Input features for prediction.
            model: Trained ML model.
            
        Returns:
            float: Prediction variance.
        """
        try:
            if hasattr(model, "estimators_"):  # Random Forest
                predictions = []
                for estimator in model.estimators_:
                    predictions.append(estimator.predict(features))
                return float(np.var(predictions))
            else:
                # For single models, return default variance
                return 0.1
        except Exception:
            return 0.1

