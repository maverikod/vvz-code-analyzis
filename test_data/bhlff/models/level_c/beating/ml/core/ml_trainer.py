"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ML model trainer for beating prediction.

This module implements ML model training for machine learning
models in 7D phase field beating analysis.

Physical Meaning:
    Trains machine learning models for predicting beating frequencies
    and mode coupling using 7D phase field theory.

Example:
    >>> trainer = MLTrainer()
    >>> trainer.train_frequency_model(n_samples=1000)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
import logging
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import os

from .training_data_generator import TrainingDataGenerator
from .ml_models import MLModelManager


class MLTrainer:
    """
    ML model trainer for beating prediction.

    Physical Meaning:
        Trains machine learning models for predicting beating frequencies
        and mode coupling using 7D phase field theory.

    Mathematical Foundation:
        Uses Random Forest regression for frequency prediction and
        Neural Network regression for coupling prediction.
    """

    def __init__(self, model_manager: Optional[MLModelManager] = None):
        """
        Initialize ML trainer.

        Physical Meaning:
            Sets up the ML training system for 7D phase field analysis.

        Args:
            model_manager (Optional[MLModelManager]): ML model manager instance.
        """
        self.model_manager = model_manager or MLModelManager()
        self.data_generator = TrainingDataGenerator()
        self.logger = logging.getLogger(__name__)

        # Training parameters
        self.test_size = 0.2
        self.random_state = 42

        # Model parameters
        self.frequency_model_params = {
            "n_estimators": 200,
            "max_depth": 15,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "random_state": self.random_state,
        }

        self.coupling_model_params = {
            "hidden_layer_sizes": (100, 50, 25),
            "max_iter": 2000,
            "learning_rate_init": 0.001,
            "random_state": self.random_state,
        }

    def train_frequency_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train frequency prediction model.

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

        # Generate training data
        X, y = self.data_generator.generate_frequency_training_data(n_samples)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state
        )

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = RandomForestRegressor(**self.frequency_model_params)
        model.fit(X_train_scaled, y_train)

        # Evaluate model
        y_pred = model.predict(X_test_scaled)
        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        # Save model
        self.model_manager.save_model("frequency", model, scaler)

        # Update model manager
        self.model_manager.frequency_model = model
        self.model_manager.frequency_scaler = scaler

        self.logger.info(
            f"Frequency model training completed. MSE: {mse:.4f}, R²: {r2:.4f}"
        )

        return {
            "model_type": "RandomForest",
            "mse": mse,
            "r2_score": r2,
            "n_samples": n_samples,
            "n_features": X.shape[1],
            "feature_importance": dict(
                zip(
                    [
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
                    ],
                    model.feature_importances_,
                )
            ),
        }

    def train_coupling_model(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train coupling prediction model.

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

        # Generate training data
        X, y = self.data_generator.generate_coupling_training_data(n_samples)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state
        )

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = MLPRegressor(**self.coupling_model_params)
        model.fit(X_train_scaled, y_train)

        # Evaluate model
        y_pred = model.predict(X_test_scaled)
        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        # Save model
        self.model_manager.save_model("coupling", model, scaler)

        # Update model manager
        self.model_manager.coupling_model = model
        self.model_manager.coupling_scaler = scaler

        self.logger.info(
            f"Coupling model training completed. MSE: {mse:.4f}, R²: {r2:.4f}"
        )

        return {
            "model_type": "NeuralNetwork",
            "mse": mse,
            "r2_score": r2,
            "n_samples": n_samples,
            "n_features": X.shape[1],
            "n_outputs": y.shape[1],
        }

    def train_all_models(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Train all ML models.

        Physical Meaning:
            Trains both frequency and coupling prediction models using
            7D phase field theory and VBP envelope configurations.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Dict[str, Any]: Training results for all models.
        """
        self.logger.info(f"Training all models with {n_samples} samples")

        # Train frequency model
        frequency_results = self.train_frequency_model(n_samples)

        # Train coupling model
        coupling_results = self.train_coupling_model(n_samples)

        return {
            "frequency_model": frequency_results,
            "coupling_model": coupling_results,
            "training_completed": True,
        }

    def validate_models(self, n_samples: int = 200) -> Dict[str, Any]:
        """
        Validate trained models.

        Physical Meaning:
            Validates trained ML models using independent test data
            to ensure prediction accuracy and reliability.

        Args:
            n_samples (int): Number of validation samples to generate.

        Returns:
            Dict[str, Any]: Validation results for all models.
        """
        self.logger.info(f"Validating models with {n_samples} samples")

        # Generate validation data
        X_freq, y_freq = self.data_generator.generate_frequency_training_data(n_samples)
        X_coup, y_coup = self.data_generator.generate_coupling_training_data(n_samples)

        # Validate frequency model
        if self.model_manager.frequency_model is not None:
            X_freq_scaled = self.model_manager.frequency_scaler.transform(X_freq)
            y_freq_pred = self.model_manager.frequency_model.predict(X_freq_scaled)
            freq_mse = mean_squared_error(y_freq, y_freq_pred)
            freq_r2 = r2_score(y_freq, y_freq_pred)
        else:
            freq_mse = None
            freq_r2 = None

        # Validate coupling model
        if self.model_manager.coupling_model is not None:
            X_coup_scaled = self.model_manager.coupling_scaler.transform(X_coup)
            y_coup_pred = self.model_manager.coupling_model.predict(X_coup_scaled)
            coup_mse = mean_squared_error(y_coup, y_coup_pred)
            coup_r2 = r2_score(y_coup, y_coup_pred)
        else:
            coup_mse = None
            coup_r2 = None

        return {
            "frequency_model": {
                "mse": freq_mse,
                "r2_score": freq_r2,
                "validation_samples": n_samples,
            },
            "coupling_model": {
                "mse": coup_mse,
                "r2_score": coup_r2,
                "validation_samples": n_samples,
            },
        }

    def get_model_performance(self) -> Dict[str, Any]:
        """
        Get model performance metrics.

        Physical Meaning:
            Returns performance metrics for trained ML models
            to assess prediction quality and reliability.

        Returns:
            Dict[str, Any]: Model performance metrics.
        """
        performance = {}

        if self.model_manager.frequency_model is not None:
            performance["frequency_model"] = {
                "model_type": "RandomForest",
                "n_estimators": self.model_manager.frequency_model.n_estimators,
                "max_depth": self.model_manager.frequency_model.max_depth,
                "feature_importance": dict(
                    zip(
                        [
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
                        ],
                        self.model_manager.frequency_model.feature_importances_,
                    )
                ),
            }

        if self.model_manager.coupling_model is not None:
            performance["coupling_model"] = {
                "model_type": "NeuralNetwork",
                "hidden_layers": self.model_manager.coupling_model.hidden_layer_sizes,
                "max_iter": self.model_manager.coupling_model.max_iter,
                "learning_rate": self.model_manager.coupling_model.learning_rate_init,
            }

        return performance
