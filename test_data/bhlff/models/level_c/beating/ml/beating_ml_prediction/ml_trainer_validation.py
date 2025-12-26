"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation methods for ML trainer.

This module provides validation methods for trained ML models,
including model evaluation and performance metrics computation.

Physical Meaning:
    Validates trained ML models using independent test data to ensure
    prediction accuracy and reliability for frequency and coupling prediction.
"""

import numpy as np
from typing import Dict, Any
import logging
from sklearn.metrics import mean_squared_error, r2_score


class MLTrainerValidation:
    """
    Validation methods for ML trainer.
    
    Physical Meaning:
        Provides methods for validating trained ML models
        and computing performance metrics.
    """
    
    def __init__(self, model_manager, data_generation, logger: logging.Logger = None):
        """
        Initialize validation methods.
        
        Args:
            model_manager: ML model manager instance.
            data_generation: Data generation instance.
            logger (logging.Logger): Logger instance.
        """
        self.model_manager = model_manager
        self.data_generation = data_generation
        self.logger = logger or logging.getLogger(__name__)
    
    def validate_frequency_model(self, n_samples: int) -> Dict[str, Any]:
        """
        Validate frequency model.
        
        Physical Meaning:
            Validates trained frequency prediction model using
            independent test data.
            
        Args:
            n_samples (int): Number of validation samples to generate.
            
        Returns:
            Dict[str, Any]: Validation results.
        """
        try:
            # Generate validation data
            X, y = self.data_generation.generate_frequency_training_data(n_samples)
            
            # Load model and scaler
            model = self.model_manager.get_frequency_model()
            scaler = self.model_manager.get_frequency_scaler()
            
            if model is not None and scaler is not None:
                # Scale features
                X_scaled = scaler.transform(X)
                
                # Make predictions
                y_pred = model.predict(X_scaled)
                
                # Compute validation metrics
                mse = mean_squared_error(y, y_pred)
                r2 = r2_score(y, y_pred)
                
                return {
                    "mse": mse,
                    "r2": r2,
                    "n_samples": n_samples,
                    "validation_successful": True,
                }
            else:
                return {"validation_successful": False, "error": "Model not available"}
                
        except Exception as e:
            self.logger.error(f"Frequency model validation failed: {e}")
            return {"validation_successful": False, "error": str(e)}
    
    def validate_coupling_model(self, n_samples: int) -> Dict[str, Any]:
        """
        Validate coupling model.
        
        Physical Meaning:
            Validates trained coupling prediction model using
            independent test data.
            
        Args:
            n_samples (int): Number of validation samples to generate.
            
        Returns:
            Dict[str, Any]: Validation results.
        """
        try:
            # Generate validation data
            X, y = self.data_generation.generate_coupling_training_data(n_samples)
            
            # Load model and scaler
            model = self.model_manager.get_coupling_model()
            scaler = self.model_manager.get_coupling_scaler()
            
            if model is not None and scaler is not None:
                # Scale features
                X_scaled = scaler.transform(X)
                
                # Make predictions
                y_pred = model.predict(X_scaled)
                
                # Compute validation metrics
                mse = mean_squared_error(y, y_pred)
                r2 = r2_score(y, y_pred)
                
                return {
                    "mse": mse,
                    "r2": r2,
                    "n_samples": n_samples,
                    "validation_successful": True,
                }
            else:
                return {"validation_successful": False, "error": "Model not available"}
                
        except Exception as e:
            self.logger.error(f"Coupling model validation failed: {e}")
            return {"validation_successful": False, "error": str(e)}

