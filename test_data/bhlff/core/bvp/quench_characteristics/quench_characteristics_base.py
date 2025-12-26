"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for quench characteristics.

This module provides the base QuenchCharacteristicsBase class with common
initialization and setup methods.
"""

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ...domain.domain_7d import Domain7D


class QuenchCharacteristicsBase:
    """
    Base class for quench characteristics computer.
    
    Physical Meaning:
        Provides base functionality for computing quench event
        characteristics in 7D space-time.
    """
    
    def __init__(self, domain_7d: Domain7D):
        """
        Initialize quench characteristics computer.
        
        Physical Meaning:
            Sets up the characteristics computer with the computational
            domain to compute quench event properties.
        
        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d
        self.cuda_available = CUDA_AVAILABLE

