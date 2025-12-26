"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for beating ML patterns old.

This module provides the base BeatingMLPatternsBase class with common
initialization and main classification methods.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from bhlff.core.bvp.bvp_core.bvp_vectorized_processor import BVPVectorizedProcessor


class BeatingMLPatternsBase:
    """
    Base class for machine learning pattern classification.
    
    Physical Meaning:
        Provides base functionality for machine learning-based pattern
        classification for analyzing beating patterns in the 7D phase field.
        
    Mathematical Foundation:
        Uses machine learning techniques for pattern recognition and classification
        of beating modes and their characteristics.
    """
    
    def __init__(self, bvp_core: BVPCore):
        """
        Initialize pattern classification analyzer.
        
        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        
        # Pattern classification parameters
        self.pattern_classification_enabled = True
        self.classification_confidence = 0.8
        
        # Initialize vectorized processor for pattern analysis
        self._setup_vectorized_processor()
    
    def classify_beating_patterns(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Classify beating patterns using machine learning.
        
        Physical Meaning:
            Classifies beating patterns in the envelope field
            using machine learning techniques for pattern recognition.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Pattern classification results.
        """
        self.logger.info("Classifying beating patterns")
        
        # Extract features
        features = self._extract_pattern_features(envelope)
        
        # Classify patterns
        if self.pattern_classification_enabled:
            classification_results = self._classify_patterns_ml(features)
        else:
            classification_results = self._classify_patterns_simple(features)
        
        self.logger.info("Pattern classification completed")
        return classification_results
    
    def _extract_pattern_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract features for pattern classification.
        
        Physical Meaning:
            Extracts relevant features from the envelope field
            for machine learning-based pattern classification.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Extracted features for classification.
        """
        # Spatial features
        spatial_features = {
            "envelope_energy": np.sum(np.abs(envelope) ** 2),
            "envelope_max": np.max(np.abs(envelope)),
            "envelope_mean": np.mean(np.abs(envelope)),
            "envelope_std": np.std(np.abs(envelope)),
        }
        
        # Frequency features
        envelope_fft = np.fft.fftn(envelope)
        frequency_spectrum = np.abs(envelope_fft)
        
        frequency_features = {
            "spectrum_peak": np.max(frequency_spectrum),
            "spectrum_mean": np.mean(frequency_spectrum),
            "spectrum_std": np.std(frequency_spectrum),
            "dominant_frequencies": np.argsort(frequency_spectrum.flatten())[
                -5:
            ].tolist(),
        }
        
        # Pattern features
        pattern_features = {
            "symmetry_score": self._calculate_symmetry_score(envelope),
            "regularity_score": self._calculate_regularity_score(envelope),
            "complexity_score": self._calculate_complexity_score(envelope),
        }
        
        return {
            "spatial_features": spatial_features,
            "frequency_features": frequency_features,
            "pattern_features": pattern_features,
        }
    
    def _setup_vectorized_processor(self) -> None:
        """
        Setup vectorized processor for pattern analysis.
        
        Physical Meaning:
            Initializes vectorized processor for 7D phase field computations
            to optimize pattern analysis performance using CUDA acceleration.
        """
        try:
            # Get domain and config from BVP core
            domain = self.bvp_core.domain
            config = self.bvp_core.config
            
            # Initialize vectorized BVP processor
            self.vectorized_processor = BVPVectorizedProcessor(
                domain=domain, config=config, block_size=8, overlap=2, use_cuda=True
            )
            
            self.logger.info("Vectorized processor initialized for pattern analysis")
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize vectorized processor: {e}")
            self.vectorized_processor = None

