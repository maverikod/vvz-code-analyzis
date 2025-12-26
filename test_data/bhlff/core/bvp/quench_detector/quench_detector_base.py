"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for quench detector.

This module provides the base QuenchDetectorBase class with common
initialization and main detect_quenches method.
"""

import numpy as np
from typing import Dict, Any
import logging

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    raise ImportError(
        "CuPy is required but not available. "
        "Please install CuPy to use CUDA acceleration: pip install cupy"
    )

from ...domain.domain_7d import Domain7D
from ..quench_thresholds import QuenchThresholdComputer
from ..quench_morphology import QuenchMorphology
from ..quench_characteristics import QuenchCharacteristics


class QuenchDetectorBase:
    """
    Base class for quench detector.
    
    Physical Meaning:
        Provides base functionality for monitoring local thresholds
        and detecting when BVP dissipatively "dumps" energy into
        the medium.
        
    Mathematical Foundation:
        Applies three threshold criteria for quench detection:
        1. Amplitude threshold: |A| > |A_q|
        2. Detuning threshold: |ω - ω_0| > Δω_q
        3. Gradient threshold: |∇A| > |∇A_q|
        where A_q, Δω_q, and ∇A_q are the quench thresholds.
    """
    
    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize quench detector.
        
        Physical Meaning:
            Sets up the quench detector with threshold parameters
            for detecting amplitude, detuning, and gradient quenches
            in the 7D BVP field.
            
        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - amplitude_threshold (float): Amplitude quench threshold |A_q|
                - detuning_threshold (float): Detuning quench threshold Δω_q
                - gradient_threshold (float): Gradient quench threshold |∇A_q|
                - carrier_frequency (float): BVP carrier frequency ω₀
        """
        self.domain_7d = domain_7d
        self.config = config
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Check CUDA availability and setup
        self.cuda_available = CUDA_AVAILABLE and config.get("use_cuda", True)
        if self.cuda_available:
            self.logger.info(
                "CUDA available - using GPU acceleration for quench detection"
            )
        else:
            self.logger.info(
                "CUDA not available - using CPU processing for quench detection"
            )
        
        # Initialize threshold computer, morphology processor, and characteristics computer
        self.threshold_computer = QuenchThresholdComputer(domain_7d)
        self.morphology = QuenchMorphology()
        self.characteristics = QuenchCharacteristics(domain_7d)
        
        # Block processing configuration
        self.block_size = int(config.get("block_size", 0))  # 0 disables blocked mode
        self.overlap = int(config.get("overlap", 2))
        self.batch_size = int(config.get("batch_size", 1))
        self.verbose = bool(config.get("verbose", True))
        self.progress_interval = int(config.get("progress_interval", 10))
        
        # Compute physical thresholds from theoretical principles
        thresholds = self.threshold_computer.compute_all_thresholds()
        self.amplitude_threshold = thresholds["amplitude_threshold"]
        self.detuning_threshold = thresholds["detuning_threshold"]
        self.gradient_threshold = thresholds["gradient_threshold"]
        self.carrier_frequency = thresholds["carrier_frequency"]
        
        # Override with config values if provided (for testing/debugging)
        if "amplitude_threshold" in config:
            self.amplitude_threshold = config["amplitude_threshold"]
        if "detuning_threshold" in config:
            self.detuning_threshold = config["detuning_threshold"]
        if "gradient_threshold" in config:
            self.gradient_threshold = config["gradient_threshold"]
        if "carrier_frequency" in config:
            self.carrier_frequency = config["carrier_frequency"]
        
        # Setup threshold validation
        self._validate_thresholds()
        
        # Auto-configure block size based on GPU memory if not specified
        if self.block_size == 0 and self.cuda_available:
            self.block_size = self._compute_optimal_block_size_from_gpu_memory()
        
        # Verbose logging level
        if self.verbose:
            self.logger.setLevel(logging.INFO)
    
    def detect_quenches(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Detect quench events based on three thresholds.
        
        Physical Meaning:
            Applies three threshold criteria to detect quench events:
            - amplitude: |A| > |A_q| - detects high-amplitude quenches
            - detuning: |ω - ω_0| > Δω_q - detects frequency detuning quenches
            - gradient: |∇A| > |∇A_q| - detects high-gradient quenches
            
        Mathematical Foundation:
            For each point in 7D space-time, checks:
            1. |A(x,φ,t)| > |A_q|
            2. |ω_local - ω_0| > Δω_q
            3. |∇A(x,φ,t)| > |∇A_q|
            where ω_local is the local frequency derived from phase evolution.
            
        Args:
            envelope (np.ndarray): 7D envelope field with shape
                (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)
                
        Returns:
            Dict[str, Any]: Quench detection results including:
                - quenches_detected (bool): Whether any quenches were found
                - quench_locations (List[Tuple]): 7D coordinates of quench events
                - quench_types (List[str]): Types of quenches detected
                - quench_strengths (List[float]): Strength of each quench
                - amplitude_quenches (List[Tuple]): Amplitude quench locations
                - detuning_quenches (List[Tuple]): Detuning quench locations
                - gradient_quenches (List[Tuple]): Gradient quench locations
        """
        # Prefer blocked processing when configured to avoid OOM
        if self.block_size and self.block_size > 0:
            self.logger.info(
                f"Blocked detection enabled: block_size={self.block_size}, overlap={self.overlap}, batch_size={self.batch_size}, cuda={self.cuda_available}"
            )
            return self._detect_quenches_blocked(envelope)
        
        # Fallback: whole-domain processing
        if self.cuda_available:
            return self._detect_quenches_cuda(envelope)
        return self._detect_quenches_cpu(envelope)

