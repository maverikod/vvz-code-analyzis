"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for ABCD model.

This module provides the base ABCDModelBase class with common
initialization and basic methods.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional, Union
import logging

from bhlff.core.bvp import BVPCore
from ...abcd import (
    ResonatorLayer,
    SystemMode,
    ABCDSpectralAnalyzer,
    ABCDTransmissionCore,
    ABCDVectorizedOps,
    ABCDBlockProcessing,
)

# Import modular components
from ..transmission_computation import ABCDTransmissionComputation
from ..spectral_analysis_poles import ABCDSpectralPolesAnalysis
from ..admittance_computation import ABCDAdmittanceComputation
from ..quality_factors import ABCDQualityFactors
from ..mode_analysis import ABCDModeAnalysis
from ..delegation_methods import ABCDDelegationMethods

# Try to import CUDA
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class ABCDModelBase:
    """
    Base class for ABCD transmission matrix model.
    
    Physical Meaning:
        Provides base functionality for implementing the transmission matrix
        method for analyzing cascaded resonators in the 7D phase field theory.
        
    Mathematical Foundation:
        Uses the ABCD matrix formalism with spectral analysis:
        - Each layer: T_ℓ = [A_ℓ  B_ℓ; C_ℓ  D_ℓ]
        - System matrix: T_total = ∏ T_ℓ
        - Resonance condition: spectral poles from 7D phase field analysis
        - Quality factors: Q = ω₀ / (2π * Δω) from spectral linewidth
        - Admittance: Y(ω) = C/A
    """
    
    def __init__(
        self,
        resonators: Optional[List[ResonatorLayer]] = None,
        bvp_core: Optional[BVPCore] = None,
    ):
        """
        Initialize ABCD model.
        
        Physical Meaning:
            Sets up ABCD model with CUDA-accelerated block processing
            using 80% of available GPU memory for optimal performance.
            Sets up the ABCD model for the given resonator chain,
            computing transmission matrices for each layer and
            preparing for system analysis.
            
        Args:
            resonators (List[ResonatorLayer]): List of resonator layers.
            bvp_core (Optional[BVPCore]): BVP core for advanced calculations.
        """
        self.resonators = resonators or []
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        
        # Initialize module instances
        self._spectral_analyzer = ABCDSpectralAnalyzer()
        self._transmission_core = ABCDTransmissionCore()
        self._vectorized_ops = ABCDVectorizedOps()
        self._block_processing = ABCDBlockProcessing()
        
        # Initialize CUDA processor for block processing with 80% GPU memory
        if self.bvp_core is not None:
            try:
                from ...cuda import LevelCCUDAProcessor
                
                self.cuda_processor = LevelCCUDAProcessor(bvp_core, use_cuda=True)
                self.use_cuda = self.cuda_processor.cuda_available
                self.block_size = self.cuda_processor.block_size
                self.logger.info(
                    f"ABCD model initialized with CUDA block processing: "
                    f"block_size={self.block_size}, using 80% GPU memory"
                )
            except Exception as e:
                self.logger.warning(
                    f"CUDA processor initialization failed: {e}, using CPU"
                )
                self.cuda_processor = None
                self.use_cuda = False
                self.block_size = 8  # Default CPU block size
        else:
            self.cuda_processor = None
            self.use_cuda = False
            self.block_size = 8
        
        # Pre-compute layer properties
        self._compute_layer_properties()
        
        # Initialize field generator for 7D spectral analysis if BVP core available
        self._field_generator = None
        if self.bvp_core is not None:
            try:
                from bhlff.core.sources.bvp_source_generators import BVPSourceGenerators
                
                if hasattr(self.bvp_core, "domain"):
                    source_config = {
                        "use_cuda": self.use_cuda,
                        "gaussian_amplitude": 1.0,
                        "gaussian_center": [0.5, 0.5, 0.5],
                        "gaussian_width": 0.1,
                    }
                    self._field_generator = BVPSourceGenerators(
                        self.bvp_core.domain, source_config
                    )
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize field generator: {e}, "
                    f"spectral analysis will use simplified methods"
                )
        
        # Initialize modular components
        self._transmission_computation = ABCDTransmissionComputation(
            self.resonators, self.bvp_core, self.use_cuda, self.logger
        )
        self._spectral_poles_analysis = ABCDSpectralPolesAnalysis(
            self.bvp_core, self.logger
        )
        self._admittance_computation = (
            None  # Will be initialized after compute_transmission_matrix is bound
        )
        self._quality_factors = (
            None  # Will be initialized after compute_resonator_determinants is bound
        )
        self._mode_analysis = (
            None  # Will be initialized after compute_transmission_matrix is bound
        )
        
        # Initialize delegation methods for backward compatibility
        # Note: Will be initialized after methods are bound
        self._delegation = None
    
    def _compute_layer_properties(self) -> None:
        """Compute properties for each layer."""
        for layer in self.resonators:
            if layer.material_params is None:
                layer.material_params = {
                    "kappa": 1.0 + layer.contrast,
                    "chi_real": 1.0,
                    "chi_imag": layer.memory_gamma,
                }

