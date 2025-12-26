"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Configuration for BVP block processing system.

This module defines the configuration dataclass that controls block processing
behaviour for the 7D BVP envelope computations.
"""

from dataclasses import dataclass


@dataclass
class BVPBlockConfig:
    """
    Configuration for BVP block processing.
    
    Physical Meaning:
        Encapsulates numerical and physical parameters that control how the
        block processing engine handles the 7D BVP envelope equation.
    """

    # Block processing settings
    block_size: int = 16
    overlap_ratio: float = 0.1
    max_memory_usage: float = 0.8

    # BVP-specific settings
    envelope_tolerance: float = 1e-6
    max_envelope_iterations: int = 100
    quench_detection_enabled: bool = True
    impedance_calculation_enabled: bool = True

    # Processing optimisation
    enable_adaptive_sizing: bool = True
    enable_memory_optimization: bool = True
    enable_parallel_processing: bool = True
    enable_gpu_acceleration: bool = True
