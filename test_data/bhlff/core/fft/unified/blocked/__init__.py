"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Blocked processing package.

This package provides blocked processing utilities for unified spectral operations.
"""

from .blocked_facade import (
    compute_optimal_7d_block_tiling,
    forward_fft_blocked,
    inverse_fft_blocked,
)

__all__ = [
    "compute_optimal_7d_block_tiling",
    "forward_fft_blocked",
    "inverse_fft_blocked",
]

