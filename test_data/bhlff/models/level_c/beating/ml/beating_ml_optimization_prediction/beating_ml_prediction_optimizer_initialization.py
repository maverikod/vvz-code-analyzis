"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Initialization methods for beating ML prediction optimization.

This module provides initialization and setup methods as a mixin class.
"""

import logging

from bhlff.core.bvp.bvp_core.bvp_vectorized_processor import BVPVectorizedProcessor


class BeatingMLPredictionOptimizerInitializationMixin:
    """Mixin providing initialization methods."""
    
    def _setup_vectorized_processor(self) -> None:
        """
        Setup vectorized processor for optimization.
        
        Physical Meaning:
            Initializes vectorized processor for 7D phase field computations
            to optimize ML prediction performance using CUDA acceleration.
        """
        if self.bvp_core is None:
            self.logger.warning(
                "BVP core not available, skipping vectorized processor initialization"
            )
            self.vectorized_processor = None
            return
        
        try:
            # Get domain and config from BVP core
            domain = self.bvp_core.domain
            config = self.bvp_core.config
            
            # Initialize vectorized BVP processor
            self.vectorized_processor = BVPVectorizedProcessor(
                domain=domain, config=config, block_size=8, overlap=2, use_cuda=True
            )
            
            self.logger.info("Vectorized processor initialized for ML optimization")
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize vectorized processor: {e}")
            self.vectorized_processor = None
    
    def _initialize_prediction_parameters(self) -> dict:
        """
        Initialize prediction parameters.
        
        Physical Meaning:
            Initializes prediction parameters with default values
            for optimization.
            
        Returns:
            Dict[str, Any]: Initial prediction parameters.
        """
        return {
            "prediction_horizon": 10,
            "feature_window": 5,
            "prediction_threshold": 0.7,
            "model_complexity": "medium",
            "regularization_strength": 0.01,
        }

