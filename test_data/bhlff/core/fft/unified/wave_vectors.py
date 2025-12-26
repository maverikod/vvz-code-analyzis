"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Wave vector utilities for unified spectral operations.
"""

from typing import List, Tuple
import numpy as np


def get_wave_vectors(domain_shape: Tuple[int, ...]) -> List[np.ndarray]:
    """
    Get 1D wave vectors for each axis based on domain shape.
    """
    k_vectors = []
    for i, n in enumerate(domain_shape):
        if i < 3:  # spatial
            k = np.fft.fftfreq(n, 1.0 / n)
        elif i < 6:  # phase
            k = np.fft.fftfreq(n, 2 * np.pi / n)
        else:  # time
            k = np.fft.fftfreq(n, 1.0 / n)
        k_vectors.append(k)
    return k_vectors


def create_wave_vector_grid(
    k_vec: np.ndarray, axis: int, shape: Tuple[int, ...]
) -> np.ndarray:
    """
    Create a broadcastable grid for the given axis embedding k_vec along that axis.
    """
    grids = np.meshgrid(
        *[np.arange(s) if i != axis else k_vec for i, s in enumerate(shape)],
        indexing="ij",
    )
    return grids[axis]
