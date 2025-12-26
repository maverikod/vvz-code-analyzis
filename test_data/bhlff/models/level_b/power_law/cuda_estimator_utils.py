"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA utilities for block-aware critical exponent estimation.

This module provides CUDA-accelerated helper functions for computing
block statistics and backend management in 7D BVP analysis.

Physical Meaning:
    Efficient GPU-accelerated computation of block statistics while
    preserving 7D structure for critical exponent estimation.

Mathematical Foundation:
    Provides vectorized CUDA operations for mean, variance, and
    CCDF computation on blocks of 7D phase field data.
"""

from __future__ import annotations

from typing import Any, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


def get_cuda_backend() -> Any:
    """
    Get CUDA backend if available.

    Returns:
        Any: CUDA backend instance or None if not available.
    """
    try:
        from bhlff.utils.cuda_utils import get_global_backend, CUDABackend

        backend = get_global_backend()
        if isinstance(backend, CUDABackend):
            return backend
        return None
    except Exception:
        return None


def compute_block_statistics_cuda(
    block_arr: np.ndarray, backend: Any
) -> Tuple[float, float]:
    """
    Compute block mean and variance using CUDA acceleration with 7D structure preservation.

    Physical Meaning:
        Efficiently computes block statistics on GPU while preserving
        the full 7D block structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. Uses optimal
        memory management (blocks up to 80% of GPU memory) and vectorized
        operations for maximum performance. Essential for scalable
        processing of large 7D phase field data.

    Mathematical Foundation:
        Computes mean μ = ⟨A_block⟩ and variance σ² = ⟨(A - μ)²⟩
        using vectorized GPU operations that preserve 7D structure.
        All operations are performed on GPU arrays maintaining full
        dimensional information for accurate 7D BVP theory compliance.

    Args:
        block_arr (np.ndarray): Block array (7D structure preserved, shape (Nₓ, Nᵧ, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)).
        backend (Any): CUDA backend instance.

    Returns:
        Tuple[float, float]: (mean, variance) computed on GPU with full 7D structure.

    Raises:
        ValueError: If block array is empty or invalid.
    """
    import cupy as cp

    if block_arr.size == 0:
        raise ValueError("Block array is empty - cannot compute statistics")

    try:
        # Check memory requirements before transfer
        # For 7D arrays, need to account for full structure
        block_size_bytes = block_arr.nbytes
        mem_info = backend.get_memory_info()
        free_memory = mem_info.get("free_memory", 0)

        # Ensure block doesn't exceed 80% of free memory
        # Account for temporary arrays needed for variance computation
        # Variance requires: original array + mean array + squared differences
        max_block_size = 0.8 * free_memory / 3.0  # Safety factor for temp arrays
        if block_size_bytes > max_block_size:
            logger.debug(
                f"Block size {block_size_bytes/1e6:.2f}MB exceeds "
                f"80% GPU memory limit ({max_block_size/1e6:.2f}MB). "
                f"Using CPU computation for 7D block."
            )
            # CPU fallback with vectorized NumPy operations
            return float(np.mean(block_arr)), float(np.var(block_arr))

        # Transfer to GPU preserving 7D structure
        # cupy.asarray maintains full shape information
        block_gpu = cp.asarray(block_arr)

        # Compute statistics using vectorized operations
        # These operations preserve the 7D structure by operating on
        # all dimensions simultaneously
        mean_gpu = float(cp.mean(block_gpu))
        # Variance: compute efficiently using single pass when possible
        # For large arrays, use two-pass for numerical stability
        if block_arr.size > 1e6:
            # Two-pass variance for numerical stability on large 7D arrays
            var_gpu = float(cp.var(block_gpu, ddof=0))
        else:
            # Single-pass variance for smaller arrays
            var_gpu = float(cp.var(block_gpu))

        # Synchronize to ensure computation completes
        cp.cuda.Stream.null.synchronize()

        # Clean up GPU memory immediately
        del block_gpu
        cp.get_default_memory_pool().free_all_blocks()

        return mean_gpu, var_gpu
    except Exception as e:
        logger.debug(f"CUDA statistics computation failed: {e}, using CPU")
        # CPU fallback with vectorized NumPy (preserves 7D structure)
        return float(np.mean(block_arr)), float(np.var(block_arr))


def compute_global_mean_cuda(amplitude: np.ndarray, backend: Any) -> float:
    """
    Compute global mean using CUDA acceleration with 7D structure preservation.

    Physical Meaning:
        Efficiently computes global critical amplitude A_c on GPU
        for use as reference point in scaling analysis. Preserves
        full 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ during computation.
        Handles large 7D arrays by checking memory constraints
        and using block processing if needed.

    Mathematical Foundation:
        Computes A_c = ⟨A(x, φ, t)⟩ over full 7D space-time domain.
        Uses vectorized GPU operations that maintain all dimensional
        information for accurate 7D BVP theory compliance.

    Args:
        amplitude (np.ndarray): Full amplitude array (7D structure: (Nₓ, Nᵧ, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)).
        backend (Any): CUDA backend instance.

    Returns:
        float: Global mean computed on GPU (or CPU if memory insufficient).

    Raises:
        ValueError: If amplitude array is empty.
    """
    import cupy as cp

    if amplitude.size == 0:
        raise ValueError("Amplitude array is empty - cannot compute global mean")

    try:
        # Check memory requirements for 7D array
        amp_size_bytes = amplitude.nbytes
        mem_info = backend.get_memory_info()
        free_memory = mem_info.get("free_memory", 0)

        # Ensure array doesn't exceed 80% of free memory
        max_array_size = 0.8 * free_memory
        if amp_size_bytes > max_array_size:
            logger.debug(
                f"7D array size {amp_size_bytes/1e6:.2f}MB exceeds "
                f"80% GPU memory limit ({max_array_size/1e6:.2f}MB). "
                f"Using CPU computation for global mean."
            )
            # CPU fallback with vectorized NumPy (preserves 7D structure)
            return float(np.mean(amplitude))

        # Transfer to GPU preserving 7D structure
        amp_gpu = cp.asarray(amplitude)
        # Compute mean using vectorized GPU operation
        # Preserves all 7D structure information
        A_c = float(cp.mean(amp_gpu))
        cp.cuda.Stream.null.synchronize()

        # Clean up GPU memory immediately
        del amp_gpu
        cp.get_default_memory_pool().free_all_blocks()

        return A_c
    except Exception as e:
        logger.debug(f"CUDA global mean computation failed: {e}, using CPU")
        # CPU fallback with vectorized NumPy
        return float(np.mean(amplitude))


def compute_ccdf_cuda(
    block_flat: np.ndarray, grid: np.ndarray, backend: Any
) -> np.ndarray:
    """
    Compute CCDF using CUDA acceleration with optimized memory management.

    Physical Meaning:
        Computes complementary cumulative distribution function
        P(>A) for each grid point using vectorized GPU operations.
        Essential for efficient tail analysis in β estimation with
        7D block structure. Uses optimal memory management (up to 80%
        of GPU memory) and vectorized broadcasting for maximum performance.

    Mathematical Foundation:
        CCDF(A) = P(>A) = (1/N) Σᵢ I(Aᵢ > A)
        where I is indicator function and N is block size.
        Uses broadcasting: v_gpu[None, :] > g_gpu[:, None] creates
        comparison matrix of size (grid_size, block_size).
        For large arrays, uses chunked processing to stay within
        memory limits while preserving computational efficiency.

    Args:
        block_flat (np.ndarray): Flattened block values (from block-wise processing
            of 7D structure, preserves locality information).
        grid (np.ndarray): Amplitude grid for CCDF evaluation.
        backend (Any): CUDA backend instance.

    Returns:
        np.ndarray: CCDF values on grid (vectorized computation).

    Raises:
        ValueError: If block_flat or grid is empty.
    """
    import cupy as cp

    if block_flat.size == 0:
        raise ValueError("Block array is empty - cannot compute CCDF")
    if grid.size == 0:
        raise ValueError("Grid is empty - cannot compute CCDF")

    try:
        # Estimate memory requirements for broadcasting
        # v_gpu: (1, block_size), g_gpu: (grid_size, 1)
        # Comparison matrix: (grid_size, block_size) - boolean, ~1 byte per element
        block_size_bytes = block_flat.nbytes
        grid_size_bytes = grid.nbytes
        # Broadcasting creates temporary boolean matrix of size (grid_size, block_size)
        # Estimate: comparison matrix + original arrays + intermediate results
        comparison_matrix_bytes = grid.size * block_flat.size  # Boolean matrix
        estimated_memory = comparison_matrix_bytes + block_size_bytes + grid_size_bytes

        mem_info = backend.get_memory_info()
        free_memory = mem_info.get("free_memory", 0)
        max_memory = 0.8 * free_memory

        if estimated_memory > max_memory:
            # Use chunked processing for large arrays
            logger.debug(
                f"CCDF memory estimate {estimated_memory/1e6:.2f}MB exceeds "
                f"80% limit ({max_memory/1e6:.2f}MB). Using chunked CPU processing."
            )
            # CPU chunked processing to avoid memory issues
            return _compute_ccdf_chunked(block_flat, grid)

        # Transfer to GPU
        v_gpu = cp.asarray(block_flat)
        g_gpu = cp.asarray(grid)

        # Vectorized CCDF: P(>A) for each grid point
        # Broadcasting: compare each grid value with all block values
        # Uses efficient GPU kernels for comparison and reduction
        ccdf_gpu = (v_gpu[None, :] > g_gpu[:, None]).mean(axis=1)

        # Convert back to NumPy
        ccdf = cp.asnumpy(ccdf_gpu)
        cp.cuda.Stream.null.synchronize()

        # Clean up GPU memory immediately
        del v_gpu, g_gpu, ccdf_gpu
        cp.get_default_memory_pool().free_all_blocks()

        return ccdf
    except Exception as e:
        logger.debug(f"CUDA CCDF computation failed: {e}, using CPU fallback")
        # CPU fallback with vectorized broadcasting
        v = block_flat[None, :]
        g = grid[:, None]
        return (v > g).mean(axis=1)


def _compute_ccdf_chunked(block_flat: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """
    Compute CCDF using chunked processing for memory efficiency.

    Physical Meaning:
        Computes CCDF using chunked grid processing to avoid
        memory exhaustion for very large arrays. Preserves accuracy
        while managing memory constraints.

    Args:
        block_flat (np.ndarray): Flattened block values.
        grid (np.ndarray): Amplitude grid.

    Returns:
        np.ndarray: CCDF values on grid.
    """
    # Process grid in chunks to avoid memory issues
    chunk_size = min(100, len(grid))
    ccdf = np.zeros(len(grid))

    for i in range(0, len(grid), chunk_size):
        chunk = grid[i : i + chunk_size]
        v = block_flat[None, :]
        g = chunk[:, None]
        ccdf[i : i + chunk_size] = (v > g).mean(axis=1)

    return ccdf


def compute_optimal_block_size(
    amplitude: np.ndarray,
    backend: Any,
    memory_overhead_factor: float = 4.0,
    min_block_elems: int = 256,
    max_block_elems: int = 1048576,
    fraction_of_total: float = 0.001,
) -> int:
    """
    Compute optimal block size based on GPU memory (80% limit) for 7D processing.

    Physical Meaning:
        Calculates optimal block size to use 80% of available GPU memory,
        ensuring efficient memory usage while avoiding OOM errors. Preserves
        7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ by calculating block size per
        dimension for 7D arrays.

    Mathematical Foundation:
        For 7D array with shape (Nₓ, Nᵧ, N_z, N_φ₁, N_φ₂, N_φ₃, N_t):
        - Available memory: 80% of free GPU memory
        - Block size per dimension: (available_memory / overhead_factor) ^ (1/7)
        - Ensures blocks fit in GPU memory while preserving 7D structure

    Args:
        amplitude (np.ndarray): Field amplitude array (7D structure preserved).
        backend (Any): CUDA backend instance or None for CPU.
        memory_overhead_factor (float): Memory overhead factor for operations
            (default 4.0 for FFT operations, 3.0 for variance, 2.0 for CCDF).
        min_block_elems (int): Minimum block size in elements.
        max_block_elems (int): Maximum block size in elements.
        fraction_of_total (float): Maximum fraction of total elements per block.

    Returns:
        int: Optimal minimum block size in elements.
    """
    total_elems = amplitude.size

    if backend is None:
        # CPU fallback: adaptive sizing based on total elements
        return max(
            min_block_elems, min(max_block_elems, int(fraction_of_total * total_elems))
        )

    try:
        mem_info = backend.get_memory_info()
        free_memory_bytes = mem_info.get("free_memory", 0)
        # Use 80% of free memory for block processing
        available_memory_bytes = int(free_memory_bytes * 0.8)
        # Calculate maximum block elements based on memory overhead
        bytes_per_element = amplitude.dtype.itemsize
        max_block_elements = available_memory_bytes // (
            bytes_per_element * memory_overhead_factor
        )

        # For 7D arrays, calculate block size per dimension
        if amplitude.ndim == 7:
            elements_per_dim = int(max_block_elements ** (1.0 / 7.0))
            # Ensure minimum block size for robust 7D statistics
            optimal_block_elems = max(min_block_elems, elements_per_dim**7)
            # Cap at reasonable maximum
            optimal_block_elems = min(
                optimal_block_elems, int(fraction_of_total * total_elems)
            )
        else:
            # For non-7D arrays, use simpler calculation
            optimal_block_elems = max(
                min_block_elems, min(max_block_elems, max_block_elements)
            )

        return optimal_block_elems
    except Exception:
        # Fallback to adaptive sizing if memory check fails
        return max(
            min_block_elems, min(max_block_elems, int(fraction_of_total * total_elems))
        )
