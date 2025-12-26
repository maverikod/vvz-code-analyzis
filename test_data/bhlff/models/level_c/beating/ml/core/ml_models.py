"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ML model management for beating prediction.

This module implements ML model loading, creation, and management
for 7D phase field beating analysis.

Physical Meaning:
    Manages machine learning models for predicting beating frequencies
    and mode coupling in the 7D phase field theory.

Example:
    >>> model_manager = MLModelManager()
    >>> model_manager.load_frequency_model()
"""

import os
import pickle
import logging
from typing import Optional, Dict, Any
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler


class MLModelManager:
    """
    ML model manager for beating prediction.

    Physical Meaning:
        Manages machine learning models for predicting beating frequencies
        and mode coupling in the 7D phase field theory.

    Mathematical Foundation:
        Handles Random Forest regression for frequency prediction and
        Neural Network regression for coupling prediction.
    """

    def __init__(self, model_dir: str = "models/ml/beating"):
        """
        Initialize ML model manager.

        Physical Meaning:
            Sets up the ML model management system with
            appropriate parameters and storage paths.

        Args:
            model_dir (str): Directory for storing ML models.
        """
        self.model_dir = model_dir
        self.logger = logging.getLogger(__name__)

        # Model storage
        self.frequency_model = None
        self.coupling_model = None
        self.frequency_scaler = StandardScaler()
        self.coupling_scaler = StandardScaler()

        # Model paths
        self.frequency_model_path = os.path.join(model_dir, "frequency_model.pkl")
        self.coupling_model_path = os.path.join(model_dir, "coupling_model.pkl")

        # Initialize models
        self._initialize_models()

    def _initialize_models(self) -> None:
        """
        Initialize ML models for prediction.

        Physical Meaning:
            Loads or creates ML models for frequency and coupling prediction
            based on 7D phase field theory.
        """
        try:
            # Create model directory if it doesn't exist
            os.makedirs(self.model_dir, exist_ok=True)

            # Load or create frequency model
            self._load_trained_model("frequency")

            # Load or create coupling model
            self._load_trained_model("coupling")

            self.logger.info("ML models initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize ML models: {e}")
            self.frequency_model = None
            self.coupling_model = None

    def _load_trained_model(self, model_type: str) -> None:
        """
        Load trained ML model for prediction.

        Physical Meaning:
            Loads pre-trained ML model for 7D phase field prediction.

        Args:
            model_type (str): Type of model to load ('frequency' or 'coupling').
        """
        model_path = getattr(self, f"{model_type}_model_path")

        if os.path.exists(model_path):
            try:
                with open(model_path, "rb") as f:
                    model_data = pickle.load(f)
                    setattr(self, f"{model_type}_model", model_data["model"])
                    setattr(self, f"{model_type}_scaler", model_data["scaler"])
                self.logger.info(f"Loaded {model_type} model from {model_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load {model_type} model: {e}")
                self._create_default_model(model_type)
        else:
            self.logger.info(f"No trained {model_type} model found, creating default")
            self._create_default_model(model_type)

    def _create_default_model(self, model_type: str) -> None:
        """
        Create default ML model for prediction.

        Physical Meaning:
            Creates default ML model for 7D phase field prediction
            when no trained model is available.

        Args:
            model_type (str): Type of model to create ('frequency' or 'coupling').
        """
        if model_type == "frequency":
            model = RandomForestRegressor(
                n_estimators=100, max_depth=10, random_state=42
            )
        else:  # coupling
            model = MLPRegressor(
                hidden_layer_sizes=(50, 25), max_iter=1000, random_state=42
            )

        setattr(self, f"{model_type}_model", model)
        self.logger.info(f"Created default {model_type} model")

    def get_frequency_model(self) -> Optional[RandomForestRegressor]:
        """
        Get frequency prediction model.

        Physical Meaning:
            Returns the trained Random Forest model for frequency prediction.

        Returns:
            Optional[RandomForestRegressor]: Frequency prediction model.
        """
        return self.frequency_model

    def get_coupling_model(self) -> Optional[MLPRegressor]:
        """
        Get coupling prediction model.

        Physical Meaning:
            Returns the trained Neural Network model for coupling prediction.

        Returns:
            Optional[MLPRegressor]: Coupling prediction model.
        """
        return self.coupling_model

    def get_frequency_scaler(self) -> StandardScaler:
        """
        Get frequency feature scaler.

        Physical Meaning:
            Returns the feature scaler for frequency prediction.

        Returns:
            StandardScaler: Frequency feature scaler.
        """
        return self.frequency_scaler

    def get_coupling_scaler(self) -> StandardScaler:
        """
        Get coupling feature scaler.

        Physical Meaning:
            Returns the feature scaler for coupling prediction.

        Returns:
            StandardScaler: Coupling feature scaler.
        """
        return self.coupling_scaler

    def save_model(self, model_type: str, model: Any, scaler: StandardScaler) -> None:
        """
        Save trained ML model.

        Physical Meaning:
            Saves trained ML model and scaler for future use.

        Args:
            model_type (str): Type of model to save ('frequency' or 'coupling').
            model: Trained ML model.
            scaler (StandardScaler): Feature scaler.
        """
        model_path = getattr(self, f"{model_type}_model_path")

        try:
            model_data = {"model": model, "scaler": scaler}

            with open(model_path, "wb") as f:
                pickle.dump(model_data, f)

            self.logger.info(f"Saved {model_type} model to {model_path}")

        except Exception as e:
            self.logger.error(f"Failed to save {model_type} model: {e}")

    def is_model_loaded(self, model_type: str) -> bool:
        """
        Check if model is loaded.

        Physical Meaning:
            Checks if the specified model type is loaded and ready for use.

        Args:
            model_type (str): Type of model to check ('frequency' or 'coupling').

        Returns:
            bool: True if model is loaded, False otherwise.
        """
        model = getattr(self, f"{model_type}_model", None)
        return model is not None
