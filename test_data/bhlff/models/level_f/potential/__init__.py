"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Utilities for multi-particle potential computation (CPU block processing).

This package contains CPU-oriented helpers for vectorized, memory-aware
block processing used by Level F potential analyzers.

Theoretical Background:
    Assists computation of effective potentials in 7D phase field theory
    by providing block-processed, vectorized kernels operating on 3D
    spatial grids with particle lists.

Example:
    from .block_cpu import compute_potential_blocked
"""


