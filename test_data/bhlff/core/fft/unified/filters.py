"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral filter mask generators for unified spectral operations.
"""

import numpy as np
from typing import Tuple
from .wave_vectors import get_wave_vectors


def _k_magnitude(domain_shape: Tuple[int, ...]) -> np.ndarray:
    k_vectors = get_wave_vectors(domain_shape)
    # Sum of squares using broadcasting via simple addition of squares
    total = None
    for k in k_vectors:
        term = k**2
        # Expand to full grid lazily by outer-sum approximation using meshgrid
        if total is None:
            total = term[:, None, None] if len(domain_shape) >= 3 else term
        else:
            # For simplicity and robustness fallback to full meshgrid
            grids = np.meshgrid(*[kv for kv in k_vectors], indexing="ij")
            total = None
            total = grids[0] ** 2
            for g in grids[1:]:
                total = total + g**2
            break
    if total is None:
        grids = np.meshgrid(*[kv for kv in k_vectors], indexing="ij")
        total = grids[0] ** 2
        for g in grids[1:]:
            total = total + g**2
    return np.sqrt(total)


def create_lowpass_filter(domain_shape: Tuple[int, ...], cutoff: float) -> np.ndarray:
    kmag = _k_magnitude(domain_shape)
    return (kmag <= cutoff).astype(float)


def create_highpass_filter(domain_shape: Tuple[int, ...], cutoff: float) -> np.ndarray:
    kmag = _k_magnitude(domain_shape)
    return (kmag >= cutoff).astype(float)


def create_bandpass_filter(
    domain_shape: Tuple[int, ...], low_cutoff: float, high_cutoff: float
) -> np.ndarray:
    kmag = _k_magnitude(domain_shape)
    return ((kmag >= low_cutoff) & (kmag <= high_cutoff)).astype(float)
