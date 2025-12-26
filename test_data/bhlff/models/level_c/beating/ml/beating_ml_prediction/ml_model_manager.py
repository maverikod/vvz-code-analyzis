"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ML model management functionality.

This module implements ML model management including model loading,
saving, and performance tracking for beating analysis.

Physical Meaning:
    Manages machine learning models for frequency and coupling prediction
    in 7D phase field theory.

Example:
    >>> manager = MLModelManager()
    >>> model = manager.get_frequency_model()
"""

import numpy as np
from typing import Dict, Any, Optional
import logging
import joblib
import os


class MLModelManager:
    """
    ML model manager for beating analysis.

    Physical Meaning:
        Manages machine learning models for frequency and coupling prediction
        in 7D phase field theory.

    Mathematical Foundation:
        Handles model persistence, loading, and performance tracking
        for ML-based beating analysis.
    """

    def __init__(self):
        """Initialize ML model manager."""
        self.logger = logging.getLogger(__name__)

        # Model storage paths
        self.model_dir = "models/beating_ml"
        self.frequency_model_path = os.path.join(self.model_dir, "frequency_model.pkl")
        self.coupling_model_path = os.path.join(self.model_dir, "coupling_model.pkl")
        self.frequency_scaler_path = os.path.join(
            self.model_dir, "frequency_scaler.pkl"
        )
        self.coupling_scaler_path = os.path.join(self.model_dir, "coupling_scaler.pkl")

        # Model performance tracking
        self.model_performance = {}

        # Ensure model directory exists
        os.makedirs(self.model_dir, exist_ok=True)

    def get_frequency_model(self):
        """Get trained frequency prediction model."""
        try:
            if os.path.exists(self.frequency_model_path):
                return joblib.load(self.frequency_model_path)
            else:
                self.logger.warning("Frequency model not found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to load frequency model: {e}")
            return None

    def get_coupling_model(self):
        """Get trained coupling prediction model."""
        try:
            if os.path.exists(self.coupling_model_path):
                return joblib.load(self.coupling_model_path)
            else:
                self.logger.warning("Coupling model not found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to load coupling model: {e}")
            return None

    def get_frequency_scaler(self):
        """Get frequency feature scaler."""
        try:
            if os.path.exists(self.frequency_scaler_path):
                return joblib.load(self.frequency_scaler_path)
            else:
                self.logger.warning("Frequency scaler not found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to load frequency scaler: {e}")
            return None

    def get_coupling_scaler(self):
        """Get coupling feature scaler."""
        try:
            if os.path.exists(self.coupling_scaler_path):
                return joblib.load(self.coupling_scaler_path)
            else:
                self.logger.warning("Coupling scaler not found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to load coupling scaler: {e}")
            return None

    def save_frequency_model(self, model, scaler):
        """Save trained frequency model and scaler."""
        try:
            joblib.dump(model, self.frequency_model_path)
            joblib.dump(scaler, self.frequency_scaler_path)
            self.logger.info("Frequency model and scaler saved")
        except Exception as e:
            self.logger.error(f"Failed to save frequency model: {e}")

    def save_coupling_model(self, model, scaler):
        """Save trained coupling model and scaler."""
        try:
            joblib.dump(model, self.coupling_model_path)
            joblib.dump(scaler, self.coupling_scaler_path)
            self.logger.info("Coupling model and scaler saved")
        except Exception as e:
            self.logger.error(f"Failed to save coupling model: {e}")

    def update_model_performance(self, model_type: str, performance: Dict[str, Any]):
        """Update model performance metrics."""
        self.model_performance[model_type] = performance

    def get_model_performance(self) -> Dict[str, Any]:
        """Get model performance metrics."""
        return self.model_performance.copy()

    def clear_models(self):
        """Clear all saved models."""
        try:
            if os.path.exists(self.frequency_model_path):
                os.remove(self.frequency_model_path)
            if os.path.exists(self.coupling_model_path):
                os.remove(self.coupling_model_path)
            if os.path.exists(self.frequency_scaler_path):
                os.remove(self.frequency_scaler_path)
            if os.path.exists(self.coupling_scaler_path):
                os.remove(self.coupling_scaler_path)
            self.logger.info("All models cleared")
        except Exception as e:
            self.logger.error(f"Failed to clear models: {e}")

    def list_available_models(self) -> Dict[str, bool]:
        """List available models."""
        return {
            "frequency_model": os.path.exists(self.frequency_model_path),
            "coupling_model": os.path.exists(self.coupling_model_path),
            "frequency_scaler": os.path.exists(self.frequency_scaler_path),
            "coupling_scaler": os.path.exists(self.coupling_scaler_path),
        }
