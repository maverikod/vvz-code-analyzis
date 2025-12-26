"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized feature extraction for ML prediction.

This module provides vectorized methods for extracting features
for ML pattern classification.

Physical Meaning:
    Extracts comprehensive features for ML pattern classification
    using vectorized operations for efficient processing.
"""

import numpy as np
from typing import Dict, Any


class VectorizedFeatureExtraction:
    """
    Vectorized feature extraction.
    
    Physical Meaning:
        Provides vectorized methods for extracting features.
    """
    
    def extract_ml_pattern_features_vectorized(
        self, features: Dict[str, Any]
    ) -> np.ndarray:
        """
        Extract ML pattern features using vectorized operations.
        
        Physical Meaning:
            Extracts comprehensive features for ML pattern classification
            using vectorized operations for efficient processing.
            
        Args:
            features (Dict[str, Any]): Extracted features.
            
        Returns:
            np.ndarray: Vectorized feature array for ML classification.
        """
        # Vectorized feature extraction
        spatial = features.get("spatial_features", {})
        frequency = features.get("frequency_features", {})
        pattern = features.get("pattern_features", {})
        
        # Vectorized feature array construction
        feature_array = np.array(
            [
                spatial.get("envelope_energy", 0.0),
                spatial.get("envelope_max", 0.0),
                spatial.get("envelope_mean", 0.0),
                spatial.get("envelope_std", 0.0),
                frequency.get("spectrum_peak", 0.0),
                frequency.get("spectrum_bandwidth", 0.0),
                frequency.get("spectrum_entropy", 0.0),
                pattern.get("symmetry_score", 0.0),
                pattern.get("regularity_score", 0.0),
                features.get("phase_coherence", 0.0),
                features.get("topological_charge", 0.0),
            ]
        )
        
        return feature_array

