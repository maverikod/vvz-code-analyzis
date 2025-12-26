"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA utilities for `CUDABlockProcessor` to keep the facade slim.

Includes: CUDA init helpers, synthetic block extraction, device info,
memory cleanup, and block size optimization helpers.
"""

from __future__ import annotations

from typing import Any, Tuple
import numpy as np

try:
    import cupy as cp
except Exception:  # pragma: no cover
    cp = None  # type: ignore


def extract_block_data_cuda(
    start_indices: Tuple[int, ...], end_indices: Tuple[int, ...]
) -> "cp.ndarray":
    """Generate synthetic complex block data on CPU and move to GPU."""
    block_shape = tuple(end - start for start, end in zip(start_indices, end_indices))
    cpu_data = np.random.random(block_shape).astype(np.complex128)
    return cp.asarray(cpu_data)


def get_cuda_device_info() -> dict:
    """Return basic CUDA device and memory info."""
    dev = cp.cuda.Device()
    return {
        "device_id": dev.id,
        "total_memory_gb": dev.mem_info[1] / 1e9,
        "free_memory_gb": dev.mem_info[0] / 1e9,
        "cupy_version": getattr(cp, "__version__", "unknown"),
    }


def cleanup_memory() -> None:
    """Free CuPy default and pinned memory pools."""
    cp.get_default_memory_pool().free_all_blocks()
    cp.get_default_pinned_memory_pool().free_all_blocks()
