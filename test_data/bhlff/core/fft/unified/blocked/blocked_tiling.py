"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block tiling computation for blocked processing.

This module provides functions for computing optimal block tiling.
"""

from typing import Tuple
import numpy as np
from bhlff.utils.cuda_utils import get_global_backend, CUDABackend
from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps
from ....domain.optimal_block_size_calculator import OptimalBlockSizeCalculator

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


def compute_optimal_7d_block_tiling(
    field_shape: Tuple[int, ...],
    gpu_memory_ratio: float = 0.8,  # Use 80% of GPU memory for speed
) -> Tuple[int, ...]:
    """
    Compute optimal 7D block tiling for GPU memory.
    
    Physical Meaning:
        Calculates optimal block size per dimension for 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring specified fraction of GPU memory
        usage (default 80%) while preserving 7D geometric structure.
        Uses unified OptimalBlockSizeCalculator for consistency.
    """
    if len(field_shape) != 7:
        # For non-7D, use simple block size on last dimension
        backend = get_global_backend()
        if not hasattr(backend, "get_memory_info"):
            return (field_shape[-1],)
        mem = backend.get_memory_info()
        allowed = int(mem.get("free_memory", mem.get("total_memory", 0)) * gpu_memory_ratio)
        slice_bytes = np.prod(field_shape[:-1]) * 16  # complex128 = 16 bytes
        if slice_bytes == 0:
            return (field_shape[-1],)
        max_slices = max(1, allowed // (slice_bytes * 4))
        return (int(min(field_shape[-1], max_slices)),)
    
    # For 7D, use unified OptimalBlockSizeCalculator for consistency
    try:
        calculator = OptimalBlockSizeCalculator(gpu_memory_ratio=gpu_memory_ratio)
        block_tiling = calculator.calculate_for_7d(
            domain_shape=field_shape,
            dtype=np.complex128,
            overhead_factor=10.0,  # Higher overhead for FFT operations
        )
        return block_tiling
    except Exception:
        # Fallback to CUDABackend7DOps if calculator fails
        backend = get_global_backend()
        if isinstance(backend, CUDABackend) and CUDA_AVAILABLE:
            try:
                ops_7d = CUDABackend7DOps()
                block_tiling = ops_7d.compute_optimal_block_tiling_7d(
                    field_shape=field_shape,
                    dtype=np.complex128,
                    memory_fraction=gpu_memory_ratio,
                    overhead_factor=10.0,
                )
                return block_tiling
            except Exception:
                pass
    
    # Fallback: compute simple block size
    backend = get_global_backend()
    if not hasattr(backend, "get_memory_info"):
        # Use reasonable default block sizes for 7D fields
        # For spatial dimensions (0-2), use larger blocks (64-128) for better GPU utilization
        # For phase/time dimensions (3-6), use smaller blocks (32-64)
        block_sizes = []
        for i, s in enumerate(field_shape):
            if i < 3:  # Spatial dimensions (x, y, z)
                # Use larger blocks for spatial dimensions (64-128)
                block_size = max(64, min(128, s // 2)) if s > 64 else s
            else:  # Phase and time dimensions
                # Keep phase/time dimensions smaller or full size
                block_size = max(32, min(s, s // 2)) if s > 32 else s
            block_sizes.append(block_size)
        return tuple(block_sizes)
    
    mem = backend.get_memory_info()
    allowed = int(mem.get("free_memory", mem.get("total_memory", 0)) * gpu_memory_ratio)
    element_bytes = 16  # complex128
    overhead_factor = 10.0
    max_elements = allowed / (element_bytes * overhead_factor)
    elements_per_dim = int(max_elements ** (1.0 / 7.0))
    # Ensure minimum block size for efficient GPU utilization
    # For spatial dimensions (0-2), use larger blocks (64-128) for better GPU utilization
    # For phase/time dimensions (3-6), use smaller blocks (32-64)
    block_sizes = []
    for i, s in enumerate(field_shape):
        if i < 3:  # Spatial dimensions (x, y, z)
            # Use larger blocks for spatial dimensions (64-128) for better GPU utilization
            block_size = max(64, min(128, min(elements_per_dim, s))) if s > 64 else s
        else:  # Phase and time dimensions
            # Use smaller blocks for phase/time dimensions (32-64)
            block_size = max(32, min(64, min(elements_per_dim, s))) if s > 32 else s
        block_sizes.append(block_size)
    return tuple(block_sizes)

