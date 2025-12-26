"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for node analyzer.

This module provides the base LevelBNodeAnalyzerBase class with common
initialization and setup methods.
"""

import numpy as np
from typing import Dict, Any, Tuple, List

# CUDA support
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class LevelBNodeAnalyzerBase:
    """
    Base class for node analyzer.
    
    Physical Meaning:
        Provides base functionality for analyzing the absence of spherical
        standing nodes in homogeneous medium and computing topological charge.
    """
    
    def __init__(self, use_cuda: bool = True):
        """
        Initialize node analyzer.
        
        Args:
            use_cuda (bool): Whether to use CUDA acceleration if available.
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        if self.use_cuda:
            self.xp = cp
        else:
            self.xp = np
        self.max_sign_changes = 1
        self.tolerance = 1e-6
        self.radius_threshold = 0.1
        self.spectral_threshold = 1e-3

