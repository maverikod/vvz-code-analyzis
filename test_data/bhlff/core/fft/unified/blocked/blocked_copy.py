"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Blocked copy operations for FFT processing.

This module provides utilities for copying arrays using maximum block sizes
for swap operations, enabling efficient memory management for large fields.
"""

from typing import Tuple
import numpy as np
import logging

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


def copy_with_max_blocks(
    source: np.ndarray,
    target: np.ndarray,
    gpu_memory_ratio: float,
    logger: logging.Logger,
) -> None:
    """
    Copy array using maximum block sizes for swap operations.
    
    Physical Meaning:
        Copies data from source to target using maximum block sizes
        (80% GPU memory) for efficient swap operations. This maximizes
        throughput while respecting memory constraints.
        
    Mathematical Foundation:
        For 7D arrays, copies in spatial blocks (first 3 dimensions)
        to minimize memory usage while maintaining data integrity.
        
    Args:
        source (np.ndarray): Source array (may be memory-mapped).
        target (np.ndarray): Target array (may be memory-mapped).
        gpu_memory_ratio (float): GPU memory ratio to use (default 0.8).
        logger (logging.Logger): Logger for debug messages.
    """
    if source.shape != target.shape:
        raise ValueError(
            f"Shape mismatch: source {source.shape} != target {target.shape}"
        )
    
    # Calculate maximum block size (80% GPU memory)
    max_block_bytes = 0
    if CUDA_AVAILABLE:
        try:
            from bhlff.utils.cuda_utils import get_global_backend
            backend = get_global_backend()
            if hasattr(backend, "get_memory_info"):
                mem_info = backend.get_memory_info()
                free_memory = mem_info.get("free_memory", 0)
                max_block_bytes = int(free_memory * gpu_memory_ratio)
        except Exception:
            # Fallback to 1GB if cannot determine GPU memory
            max_block_bytes = 1024 * 1024 * 1024
    
    if max_block_bytes == 0:
        max_block_bytes = 1024 * 1024 * 1024  # 1GB fallback
    
    # Calculate block size in elements
    bytes_per_element = source.dtype.itemsize
    max_block_elements = max_block_bytes // bytes_per_element
    
    # For 7D arrays, copy in spatial blocks (first 3 dimensions)
    # Use maximum block size for spatial dimensions
    if len(source.shape) == 7:
        N_x, N_y, N_z = source.shape[:3]
        phase_temporal_size = np.prod(source.shape[3:])
        
        # Calculate spatial block size
        max_spatial_elements = max_block_elements // phase_temporal_size
        if max_spatial_elements < 1:
            max_spatial_elements = 1
        
        # Calculate block size per spatial dimension
        block_size_per_dim = int(max_spatial_elements ** (1.0 / 3.0))
        block_x = max(32, min(block_size_per_dim, N_x))
        block_y = max(32, min(block_size_per_dim, N_y))
        block_z = max(32, min(block_size_per_dim, N_z))
        
        logger.info(
            f"Copying with spatial blocks: ({block_x}, {block_y}, {block_z}) "
            f"= {block_x * block_y * block_z * phase_temporal_size / 1e6:.1f}M elements"
        )
        
        # Copy in spatial blocks
        for x_start in range(0, N_x, block_x):
            x_end = min(x_start + block_x, N_x)
            for y_start in range(0, N_y, block_y):
                y_end = min(y_start + block_y, N_y)
                for z_start in range(0, N_z, block_z):
                    z_end = min(z_start + block_z, N_z)
                    
                    # Copy block
                    source_block = source[x_start:x_end, y_start:y_end, z_start:z_end, :, :, :, :]
                    target[x_start:x_end, y_start:y_end, z_start:z_end, :, :, :, :] = source_block
                    
                    # Verify block was copied correctly
                    target_block = target[x_start:x_end, y_start:y_end, z_start:z_end, :, :, :, :]
                    if not np.allclose(source_block, target_block, rtol=1e-10, atol=1e-10):
                        max_diff = np.max(np.abs(source_block - target_block))
                        logger.warning(
                            f"Block copy verification failed at ({x_start}:{x_end}, {y_start}:{y_end}, {z_start}:{z_end}): "
                            f"max difference = {max_diff:.2e}"
                        )
                    
                    # Free GPU memory if using CUDA
                    if CUDA_AVAILABLE:
                        cp.get_default_memory_pool().free_all_blocks()
    else:
        # For non-7D arrays, copy directly
        target[:] = source

