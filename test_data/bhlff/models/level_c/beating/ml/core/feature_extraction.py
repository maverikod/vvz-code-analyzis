"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Feature extraction for ML prediction.

This module implements feature extraction methods for machine learning
prediction in 7D phase field beating analysis.

Physical Meaning:
    Extracts comprehensive features from 7D phase field configurations
    for machine learning prediction of beating frequencies and mode coupling.

Example:
    >>> extractor = FeatureExtractor()
    >>> features = extractor.extract_frequency_features(envelope)
"""

import numpy as np
from typing import Dict, Any

from .feature_calculators import FeatureCalculator
from .phase_field_features import PhaseFieldFeatures
from .feature_extraction_frequency import FrequencyFeatureExtractor
from .feature_extraction_coupling import CouplingFeatureExtractor
from .feature_extraction_advanced import AdvancedFeatureExtractor
from .feature_extraction_models import FeatureExtractionModels


class FeatureExtractor:
    """
    Feature extractor for ML prediction.

    Physical Meaning:
        Extracts comprehensive features from 7D phase field configurations
        for machine learning prediction of beating frequencies and mode coupling.

    Mathematical Foundation:
        Implements spectral, spatial, and temporal feature extraction
        methods based on 7D phase field theory.
    """

    def __init__(self):
        """
        Initialize feature extractor.

        Physical Meaning:
            Sets up the feature extraction system for 7D phase field analysis.
        """
        self.calculator = FeatureCalculator()
        self.phase_features = PhaseFieldFeatures()
        
        # Initialize specialized extractors
        self.frequency_extractor = FrequencyFeatureExtractor(
            self.calculator, self.phase_features
        )
        self.coupling_extractor = CouplingFeatureExtractor(
            self.calculator, self.phase_features
        )
        self.advanced_extractor = AdvancedFeatureExtractor()
        self.models_manager = FeatureExtractionModels()

    def extract_frequency_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract frequency features from envelope.

        Physical Meaning:
            Extracts frequency-related features from envelope
            for ML prediction of beating frequencies.

        Mathematical Foundation:
            Computes spectral entropy, frequency spacing, bandwidth,
            and autocorrelation from 7D phase field configuration.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency features dictionary.
        """
        return self.frequency_extractor.extract_frequency_features(envelope)

    def extract_coupling_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract coupling features from envelope.

        Physical Meaning:
            Extracts coupling-related features from envelope
            for ML prediction of mode coupling.

        Mathematical Foundation:
            Computes coupling strength, interaction energy, symmetry,
            nonlinear strength, mixing degree, and efficiency from 7D phase field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Coupling features dictionary.
        """
        return self.coupling_extractor.extract_coupling_features(envelope)

    def extract_7d_phase_features(self, features: Dict[str, Any]) -> np.ndarray:
        """
        Extract 7D phase field features for ML prediction.

        Physical Meaning:
            Extracts comprehensive 7D phase field features
            for machine learning prediction.

        Mathematical Foundation:
            Combines spectral, spatial, and temporal features
            from the 7D phase field configuration.

        Args:
            features (Dict[str, Any]): Input features dictionary.

        Returns:
            np.ndarray: 7D phase field features array.
        """
        # Extract basic features
        basic_features = [
            features.get("spectral_entropy", 0.0),
            features.get("frequency_spacing", 0.0),
            features.get("frequency_bandwidth", 0.0),
            features.get("autocorrelation", 0.0),
        ]

        # Extract coupling features
        coupling_features = [
            features.get("coupling_strength", 0.0),
            features.get("interaction_energy", 0.0),
            features.get("coupling_symmetry", 0.0),
            features.get("nonlinear_strength", 0.0),
            features.get("mixing_degree", 0.0),
            features.get("coupling_efficiency", 0.0),
        ]

        # Extract 7D phase field features
        phase_field_features = [
            features.get("phase_coherence", 0.0),
            features.get("topological_charge", 0.0),
            features.get("energy_density", 0.0),
            features.get("phase_velocity", 0.0),
        ]

        # Combine all features
        all_features = basic_features + coupling_features + phase_field_features

        return np.array(all_features)

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
        return self.models_manager.load_trained_models(model_path)
    
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
        return self.models_manager.save_trained_models(models, model_path)
    
    def extract_7d_phase_features_advanced(
        self, envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Extract advanced 7D phase field features for ML prediction.

        Physical Meaning:
            Extracts comprehensive 7D phase field features including
            topological charge, phase coherence, and energy density
            for advanced ML prediction.

        Mathematical Foundation:
            Uses 7D phase field theory to compute advanced features
            including topological invariants and phase field properties.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Advanced 7D phase field features.
        """
        return self.advanced_extractor.extract_7d_phase_features_advanced(envelope)
