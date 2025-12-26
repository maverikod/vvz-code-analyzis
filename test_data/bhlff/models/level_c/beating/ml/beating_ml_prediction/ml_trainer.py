"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ML trainer functionality.

This module implements ML trainer for model training including
data generation, model training, and performance evaluation.

Physical Meaning:
    Provides ML trainer for training machine learning models
    for beating frequency and mode coupling prediction in 7D phase field theory.

Example:
    >>> trainer = MLTrainer(model_manager)
    >>> results = trainer.train_frequency_model(n_samples=1000)
"""

import numpy as np
from typing import Dict, Any, Tuple
import logging
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
from .ml_trainer_data_generation import MLTrainerDataGeneration
from .ml_trainer_validation import MLTrainerValidation


class MLTrainer:
    """
    ML trainer for beating analysis models.

    Physical Meaning:
        Provides ML trainer for training machine learning models
        for beating frequency and mode coupling prediction in 7D phase field theory.

    Mathematical Foundation:
        Implements data generation, model training, and performance evaluation
        for ML-based prediction analysis.
    """

    def __init__(self, model_manager):
        """
        Initialize ML trainer.

        Args:
            model_manager: ML model manager instance.
        """
        self.model_manager = model_manager
        self.logger = logging.getLogger(__name__)
        
        # Initialize helper classes
        self.data_generation = MLTrainerDataGeneration(self.logger)
        self.validation = MLTrainerValidation(
            model_manager, self.data_generation, self.logger
        )

    def train_frequency_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train frequency prediction model.

        Physical Meaning:
            Trains Random Forest model for frequency prediction using
            7D phase field theory and synthetic data generation.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results and model performance.
        """
        try:
            self.logger.info(f"Training frequency model with {n_samples} samples")

            # Generate training data
            X, y = self.data_generation.generate_frequency_training_data(n_samples)

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Train model
            model = RandomForestRegressor(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
            )
            model.fit(X_train_scaled, y_train)

            # Evaluate model
            y_pred = model.predict(X_test_scaled)
            mse = mean_squared_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)

            # Save model and scaler
            self.model_manager.save_frequency_model(model, scaler)

            # Update performance
            performance = {
                "mse": mse,
                "r2": r2,
                "n_samples": n_samples,
                "model_type": "RandomForest",
            }
            self.model_manager.update_model_performance("frequency", performance)

            self.logger.info(f"Frequency model training completed. R² = {r2:.3f}")

            return {"success": True, "performance": performance, "model_saved": True}

        except Exception as e:
            self.logger.error(f"Frequency model training failed: {e}")
            return {"success": False, "error": str(e)}

    def train_coupling_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train coupling prediction model.

        Physical Meaning:
            Trains Neural Network model for coupling prediction using
            7D phase field theory and synthetic data generation.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results and model performance.
        """
        try:
            self.logger.info(f"Training coupling model with {n_samples} samples")

            # Generate training data
            X, y = self.data_generation.generate_coupling_training_data(n_samples)

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Train model
            model = MLPRegressor(
                hidden_layer_sizes=(100, 50), max_iter=1000, random_state=42
            )
            model.fit(X_train_scaled, y_train)

            # Evaluate model
            y_pred = model.predict(X_test_scaled)
            mse = mean_squared_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)

            # Save model and scaler
            self.model_manager.save_coupling_model(model, scaler)

            # Update performance
            performance = {
                "mse": mse,
                "r2": r2,
                "n_samples": n_samples,
                "model_type": "NeuralNetwork",
            }
            self.model_manager.update_model_performance("coupling", performance)

            self.logger.info(f"Coupling model training completed. R² = {r2:.3f}")

            return {"success": True, "performance": performance, "model_saved": True}

        except Exception as e:
            self.logger.error(f"Coupling model training failed: {e}")
            return {"success": False, "error": str(e)}

    def train_all_models(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train all ML models.

        Physical Meaning:
            Trains both frequency and coupling prediction models using
            7D phase field theory and synthetic data generation.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results for all models.
        """
        try:
            self.logger.info(f"Training all models with {n_samples} samples")

            # Train frequency model
            frequency_results = self.train_frequency_model(n_samples)

            # Train coupling model
            coupling_results = self.train_coupling_model(n_samples)

            return {
                "frequency_model": frequency_results,
                "coupling_model": coupling_results,
                "all_models_trained": True,
            }

        except Exception as e:
            self.logger.error(f"All models training failed: {e}")
            return {"all_models_trained": False, "error": str(e)}

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
        try:
            self.logger.info(f"Validating models with {n_samples} samples")

            # Validate frequency model
            frequency_validation = self.validation.validate_frequency_model(n_samples)

            # Validate coupling model
            coupling_validation = self.validation.validate_coupling_model(n_samples)

            return {
                "frequency_validation": frequency_validation,
                "coupling_validation": coupling_validation,
                "validation_completed": True,
            }

        except Exception as e:
            self.logger.error(f"Model validation failed: {e}")
            return {"validation_completed": False, "error": str(e)}

    def get_model_performance(self) -> Dict[str, Any]:
        """Get model performance metrics."""
        return self.model_manager.get_model_performance()
