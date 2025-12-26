"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spatial feature extraction for pattern classification.

This module provides methods for extracting spatial features
from 7D phase field configurations.

Physical Meaning:
    Extracts spatial characteristics from 7D phase field configuration
    including energy distribution and envelope properties.
"""

import numpy as np
from typing import Dict, Any


class SpatialFeatureExtraction:
    """
    Spatial feature extraction.
    
    Physical Meaning:
        Provides methods for extracting spatial features.
    """
    
    def extract_spatial_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract spatial features from envelope.
        
        Physical Meaning:
            Extracts spatial characteristics from 7D phase field configuration
            including energy distribution and envelope properties.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Spatial features dictionary.
        """
        return {
            "envelope_energy": np.sum(np.abs(envelope) ** 2),
            "envelope_max": np.max(np.abs(envelope)),
            "envelope_mean": np.mean(np.abs(envelope)),
            "envelope_std": np.std(np.abs(envelope)),
        }

