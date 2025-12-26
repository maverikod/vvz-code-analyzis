"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning pattern classification for beating analysis.

This module implements machine learning-based pattern classification
for analyzing beating patterns in the 7D phase field.

Physical Meaning:
    Provides machine learning-based pattern classification functions
    for analyzing beating patterns in the 7D phase field.

Mathematical Foundation:
    Uses machine learning techniques for pattern recognition and classification
    of beating modes and their characteristics.

Example:
    >>> patterns = BeatingMLPatterns(bvp_core)
    >>> result = patterns.classify_beating_patterns(envelope)
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore
from bhlff.core.bvp.bvp_core.bvp_vectorized_processor import BVPVectorizedProcessor
from bhlff.core.domain.vectorized_block_processor import VectorizedBlockProcessor
from .beating_ml_pattern_feature_extractor import BeatingMLPatternFeatureExtractor
from .beating_ml_pattern_classifier import BeatingMLPatternClassifier


class BeatingMLPatterns:
    """
    Machine learning pattern classification for beating analysis.

    Physical Meaning:
        Provides machine learning-based pattern classification functions
        for analyzing beating patterns in the 7D phase field.

    Mathematical Foundation:
        Uses machine learning techniques for pattern recognition and classification
        of beating modes and their characteristics.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize pattern classification analyzer.

        Physical Meaning:
            Sets up the pattern classification system for 7D phase field analysis.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Pattern classification parameters
        self.pattern_classification_enabled = True
        self.classification_confidence = 0.8

        # Initialize components
        self.feature_extractor = BeatingMLPatternFeatureExtractor(bvp_core)
        self.pattern_classifier = BeatingMLPatternClassifier(bvp_core)

        # Initialize vectorized processor for pattern analysis
        self._setup_vectorized_processor()

    def classify_beating_patterns(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Classify beating patterns using machine learning.

        Physical Meaning:
            Classifies beating patterns in the envelope field
            using machine learning techniques for pattern recognition.

        Mathematical Foundation:
            Uses machine learning algorithms for pattern recognition and classification
            of beating modes and their characteristics based on 7D phase field theory.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Pattern classification results.
        """
        self.logger.info("Classifying beating patterns")

        # Extract features
        features = self.feature_extractor.extract_pattern_features(envelope)

        # Classify patterns
        classification_results = self.pattern_classifier.classify_patterns(features)

        self.logger.info("Pattern classification completed")
        return classification_results

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
