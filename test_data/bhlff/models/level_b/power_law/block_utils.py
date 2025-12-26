"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block utilities for memory-aware 7D processing in BVP analysis.

This module yields ND slices for block-wise processing without global
flattening, keeping within approximately 80% of available memory.

Physical Meaning:
    Preserving locality and block structure is essential for correct
    evaluation of correlations and scaling properties in 7D fields.

Example:
    >>> for slc in iter_blocks(array):
    ...     sub = array[slc]
"""

from __future__ import annotations

from itertools import product
import numpy as np


def iter_blocks(array: np.ndarray, max_blocks_per_axis: int = 6):
    """
    Yield block slices to traverse the N-D array without flattening.

    The number of blocks per axis is chosen to keep block memory usage
    within a cap derived from available memory and not exceed the maximum
    number of splits per axis. This aims to keep GPU usage under ~80%.

    Args:
        array (np.ndarray): Input N-D array.
        max_blocks_per_axis (int): Maximum splits per axis.

    Yields:
        tuple[slice, ...]: Slices for the next block.
    """
    shape = array.shape
    itemsize = array.dtype.itemsize if hasattr(array, "dtype") else 8

    try:
        from bhlff.utils.cuda_utils import get_global_backend, CUDABackend

        backend = get_global_backend()
        mem_info = backend.get_memory_info()
        free_bytes = float(mem_info.get("free_memory", 0))
        if isinstance(backend, CUDABackend):
            cap_bytes = 0.8 * free_bytes / 4.0
        else:
            cap_bytes = 0.8 * free_bytes / 3.0
    except Exception:
        cap_bytes = float(256 * 1024 * 1024)

    splits = [1] * len(shape)

    def block_elems(splits_local):
        size = 1
        for n, k in zip(shape, splits_local):
            size *= int(np.ceil(n / k))
        return size

    while block_elems(splits) * itemsize > cap_bytes:
        extents = [n / k for n, k in zip(shape, splits)]
        axis = int(np.argmax(extents))
        if splits[axis] >= max_blocks_per_axis:
            sorted_axes = np.argsort(extents)[::-1]
            updated = False
            for ax in sorted_axes:
                if splits[ax] < max_blocks_per_axis:
                    splits[ax] += 1
                    updated = True
                    break
            if not updated:
                break
        else:
            splits[axis] += 1

    edges_per_axis = []
    for n, k in zip(shape, splits):
        bounds = np.linspace(0, n, k + 1, dtype=int)
        edges_per_axis.append([(bounds[i], bounds[i + 1]) for i in range(k)])

    for idxs in product(*edges_per_axis):
        slices = tuple(slice(i0, i1) for (i0, i1) in idxs)
        yield slices
