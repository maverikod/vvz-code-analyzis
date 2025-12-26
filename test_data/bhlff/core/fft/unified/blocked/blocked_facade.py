"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade module for blocked processing.

This module provides the main interface for blocked processing functions.
"""

from .blocked_tiling import compute_optimal_7d_block_tiling
from .blocked_forward import forward_fft_blocked
from .blocked_inverse import inverse_fft_blocked

__all__ = [
    "compute_optimal_7d_block_tiling",
    "forward_fft_blocked",
    "inverse_fft_blocked",
]

