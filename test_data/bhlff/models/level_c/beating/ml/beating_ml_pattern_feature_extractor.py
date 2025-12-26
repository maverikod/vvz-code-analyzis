"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Feature extractor for ML pattern classification.

This module implements feature extraction for machine learning
pattern classification in 7D phase field beating analysis.

Physical Meaning:
    Extracts comprehensive features from 7D phase field configurations
    for machine learning-based pattern classification.

Example:
    >>> extractor = BeatingMLPatternFeatureExtractor()
    >>> features = extractor.extract_pattern_features(envelope)
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from .pattern_feature_spatial import SpatialFeatureExtraction
from .pattern_feature_frequency import FrequencyFeatureExtraction
from .pattern_feature_helpers import PatternFeatureHelpers
from .pattern_feature_scores import PatternScoreComputation


class BeatingMLPatternFeatureExtractor:
    """
    Feature extractor for ML pattern classification.

    Physical Meaning:
        Extracts comprehensive features from 7D phase field configurations
        for machine learning-based pattern classification.

    Mathematical Foundation:
        Implements feature extraction methods based on 7D phase field theory
        including spatial, frequency, and pattern characteristics.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize feature extractor.

        Physical Meaning:
            Sets up the feature extraction system for 7D phase field analysis.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        
        # Initialize specialized extraction classes
        self.spatial_extraction = SpatialFeatureExtraction()
        self.frequency_extraction = FrequencyFeatureExtraction()
        self.helpers = PatternFeatureHelpers()
        self.score_computation = PatternScoreComputation(self.helpers)

    def extract_pattern_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract features for pattern classification.

        Physical Meaning:
            Extracts relevant features from the envelope field
            for machine learning-based pattern classification.

        Mathematical Foundation:
            Computes spatial, frequency, and pattern features based on
            7D phase field theory and VBP envelope analysis.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Extracted features for classification.
        """
        # Spatial features
        spatial_features = self.spatial_extraction.extract_spatial_features(envelope)
        
        # Frequency features
        frequency_features = self.frequency_extraction.extract_frequency_features(
            envelope
        )
        
        # Pattern features
        pattern_features = self.extract_pattern_characteristics(envelope)

        return {
            "spatial_features": spatial_features,
            "frequency_features": frequency_features,
            "pattern_features": pattern_features,
        }

    def extract_pattern_characteristics(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract pattern characteristics from envelope.
        
        Physical Meaning:
            Extracts pattern characteristics from 7D phase field configuration
            including symmetry, regularity, and complexity scores.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Pattern characteristics dictionary.
        """
        return {
            "symmetry_score": self.score_computation.calculate_symmetry_score(envelope),
            "regularity_score": self.score_computation.calculate_regularity_score(
                envelope
            ),
            "complexity_score": self.score_computation.calculate_complexity_score(
                envelope
            ),
        }
