"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Model management for feature extraction.

This module provides methods for loading and saving trained ML models
for feature extraction and prediction.

Physical Meaning:
    Manages trained ML models for 7D phase field prediction including
    frequency and coupling prediction models, enabling model persistence
    and reuse.
"""

import logging
import pickle
import os
from typing import Dict, Any


class FeatureExtractionModels:
    """
    Model management for feature extraction.
    
    Physical Meaning:
        Provides methods for loading and saving trained ML models
        for feature extraction and prediction.
    """
    
    def __init__(self, logger: logging.Logger = None):
        """
        Initialize model management.
        
        Args:
            logger (logging.Logger): Logger instance.
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def load_trained_models(
        self, model_path: str = "models/ml/beating/"
    ) -> Dict[str, Any]:
        """
        Load trained ML models for prediction.
        
        Physical Meaning:
            Loads pre-trained ML models for 7D phase field prediction
            including frequency and coupling prediction models.
            
        Args:
            model_path (str): Path to model directory.
            
        Returns:
            Dict[str, Any]: Loaded models and scalers.
        """
        models = {}
        
        try:
            # Load frequency model
            freq_model_path = os.path.join(model_path, "frequency_model.pkl")
            if os.path.exists(freq_model_path):
                with open(freq_model_path, "rb") as f:
                    freq_data = pickle.load(f)
                    models["frequency_model"] = freq_data.get("model")
                    models["frequency_scaler"] = freq_data.get("scaler")
            
            # Load coupling model
            coup_model_path = os.path.join(model_path, "coupling_model.pkl")
            if os.path.exists(coup_model_path):
                with open(coup_model_path, "rb") as f:
                    coup_data = pickle.load(f)
                    models["coupling_model"] = coup_data.get("model")
                    models["coupling_scaler"] = coup_data.get("scaler")
            
            # Load pattern classifier
            pattern_model_path = os.path.join(model_path, "pattern_classifier.pkl")
            if os.path.exists(pattern_model_path):
                with open(pattern_model_path, "rb") as f:
                    pattern_data = pickle.load(f)
                    models["pattern_classifier"] = pattern_data.get("model")
                    models["pattern_scaler"] = pattern_data.get("scaler")
            
            return models
            
        except Exception as e:
            self.logger.warning(f"Failed to load trained models: {e}")
            return {}
    
    def save_trained_models(
        self, models: Dict[str, Any], model_path: str = "models/ml/beating/"
    ) -> bool:
        """
        Save trained ML models for future use.
        
        Physical Meaning:
            Saves trained ML models for 7D phase field prediction
            to enable future predictions without retraining.
            
        Args:
            models (Dict[str, Any]): Models and scalers to save.
            model_path (str): Path to model directory.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Create model directory if it doesn't exist
            os.makedirs(model_path, exist_ok=True)
            
            # Save frequency model
            if "frequency_model" in models and "frequency_scaler" in models:
                freq_data = {
                    "model": models["frequency_model"],
                    "scaler": models["frequency_scaler"],
                }
                with open(os.path.join(model_path, "frequency_model.pkl"), "wb") as f:
                    pickle.dump(freq_data, f)
            
            # Save coupling model
            if "coupling_model" in models and "coupling_scaler" in models:
                coup_data = {
                    "model": models["coupling_model"],
                    "scaler": models["coupling_scaler"],
                }
                with open(os.path.join(model_path, "coupling_model.pkl"), "wb") as f:
                    pickle.dump(coup_data, f)
            
            # Save pattern classifier
            if "pattern_classifier" in models and "pattern_scaler" in models:
                pattern_data = {
                    "model": models["pattern_classifier"],
                    "scaler": models["pattern_scaler"],
                }
                with open(
                    os.path.join(model_path, "pattern_classifier.pkl"), "wb"
                ) as f:
                    pickle.dump(pattern_data, f)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save trained models: {e}")
            return False

