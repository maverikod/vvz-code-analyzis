"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Frequency feature extraction for ML prediction.

This module provides methods for extracting frequency-related features
from 7D phase field configurations for ML prediction.

Physical Meaning:
    Extracts frequency-related features including spectral entropy,
    frequency spacing, bandwidth, and autocorrelation from 7D phase
    field configurations for beating frequency prediction.
"""

import numpy as np
from typing import Dict, Any
from .feature_calculators import FeatureCalculator
from .phase_field_features import PhaseFieldFeatures


class FrequencyFeatureExtractor:
    """
    Frequency feature extractor for ML prediction.
    
    Physical Meaning:
        Provides methods for extracting frequency-related features
        from 7D phase field configurations.
    """
    
    def __init__(self, calculator: FeatureCalculator, phase_features: PhaseFieldFeatures):
        """
        Initialize frequency feature extractor.
        
        Args:
            calculator: Feature calculator instance.
            phase_features: Phase field features instance.
        """
        self.calculator = calculator
        self.phase_features = phase_features
    
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
        # Calculate spectral entropy
        spectral_entropy = self.calculator.calculate_spectral_entropy(envelope)
        
        # Calculate frequency spacing
        frequency_spacing = self.calculator.calculate_frequency_spacing(
            envelope, envelope.shape
        )
        
        # Calculate frequency bandwidth
        frequency_bandwidth = self.calculator.calculate_frequency_bandwidth(envelope)
        
        # Calculate autocorrelation
        autocorrelation = self.calculator.calculate_autocorrelation(envelope)
        
        # Calculate 7D phase field features
        phase_coherence = self.phase_features._compute_phase_coherence(
            {
                "coupling_symmetry": 0.0,  # Will be computed in coupling features
                "autocorrelation": autocorrelation,
            }
        )
        topological_charge = self.phase_features._compute_topological_charge(
            {
                "mixing_degree": 0.0,  # Will be computed in coupling features
                "nonlinear_strength": 0.0,  # Will be computed in coupling features
            }
        )
        
        return {
            "spectral_entropy": spectral_entropy,
            "frequency_spacing": frequency_spacing,
            "frequency_bandwidth": frequency_bandwidth,
            "autocorrelation": autocorrelation,
            "phase_coherence": phase_coherence,
            "topological_charge": topological_charge,
        }

