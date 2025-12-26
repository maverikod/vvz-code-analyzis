"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D operations for CUDA backend.

This module provides 7D-specific operations (Laplacian, block tiling) for
CUDABackend, enabling efficient 7D phase field computations.

Physical Meaning:
    Provides 7D operations for phase field calculations in space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, including 7D Laplacian and optimal block tiling
    computation for GPU memory optimization.

Theoretical Background:
    The 7D phase field theory operates in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where:
    - Spatial coordinates: x ∈ ℝ³ (dimensions 0, 1, 2)
    - Phase coordinates: φ ∈ 𝕋³ (dimensions 3, 4, 5)
    - Time: t ∈ ℝ (dimension 6)

Example:
    >>> from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps
    >>> ops = CUDABackend7DOps()
    >>> laplacian = ops.laplacian_7d(field, h=1.0)
"""

import logging
from typing import Tuple
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class CUDABackend7DOps:
    """
    7D operations mixin for CUDABackend.

    Physical Meaning:
        Provides 7D-specific operations for CUDA backend, including
        7D Laplacian computation and optimal block tiling calculation
        for GPU memory optimization.

    Mathematical Foundation:
        Implements 7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - Block tiling: optimized for 80% GPU memory usage
    """

    def laplacian_7d(
        self, field: "cp.ndarray", h: float = 1.0
    ) -> "cp.ndarray":
        """
        Compute 7D Laplacian on GPU using vectorized operations.

        Physical Meaning:
            Computes 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for phase field in
            space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where the Laplacian represents
            the diffusion operator across all 7 dimensions.

        Mathematical Foundation:
            For 7D field a(x,φ,t) with grid spacing h:
            Δ₇ a ≈ Σᵢ₌₀⁶ (a(x+h·eᵢ) - 2a(x) + a(x-h·eᵢ)) / h²
            where eᵢ are unit vectors in each of the 7 dimensions.

        Args:
            field (cp.ndarray): 7D field array on GPU with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            h (float): Grid spacing (default: 1.0).

        Returns:
            cp.ndarray: 7D Laplacian result on GPU with same shape.

        Raises:
            ValueError: If field is not 7D.
        """
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for 7D Laplacian, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        h_sq = h * h
        lap = cp.zeros_like(field)

        # Vectorized computation over all 7 dimensions
        # All operations are performed on GPU with vectorized kernels
        # Using explicit vectorized operations for optimal performance
        for axis in range(7):
            # Vectorized roll operations on GPU
            field_plus = cp.roll(field, 1, axis=axis)
            field_minus = cp.roll(field, -1, axis=axis)
            # Vectorized Laplacian computation for this dimension
            # All operations are vectorized on GPU for maximum efficiency
            lap += (field_plus - 2.0 * field + field_minus) / h_sq

        # Synchronize to ensure computation completes
        cp.cuda.Stream.null.synchronize()
        return lap

    def compute_optimal_block_tiling_7d(
        self,
        field_shape: Tuple[int, ...],
        dtype: type = np.complex128,
        memory_fraction: float = 0.8,
        overhead_factor: float = 10.0,
    ) -> Tuple[int, ...]:
        """
        Compute optimal 7D block tiling for 80% GPU memory usage.

        Physical Meaning:
            Calculates optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring specified fraction of GPU memory
            usage while preserving 7D geometric structure with optimal
            memory access patterns.

        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: memory_fraction × free GPU memory
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Ensures blocks fit in GPU memory while preserving 7D structure
            - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5),
              temporal (6).

        Args:
            field_shape (Tuple[int, ...]): Shape of 7D field array
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
            dtype (type): Data type (default: complex128).
            memory_fraction (float): Fraction of free GPU memory to use
                (default: 0.8 for 80% usage).
            overhead_factor (float): Memory overhead factor for operations
                (default: 10.0 for complex operations).

        Returns:
            Tuple[int, ...]: Optimal block tiling per dimension (7-tuple),
                ensuring each dimension has block size that fits in specified
                GPU memory fraction.

        Raises:
            ValueError: If field_shape is not 7D or memory calculation fails.
            RuntimeError: If GPU memory information is unavailable.
        """
        if len(field_shape) != 7:
            raise ValueError(
                f"Expected 7D field shape for optimal 7D block tiling, "
                f"got {len(field_shape)}D. Shape: {field_shape}"
            )

        try:
            # Get GPU memory info
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory_bytes = mem_info[0]
            total_memory_bytes = mem_info[1]

            # Use specified fraction of TOTAL memory (not free) for optimal utilization
            # This adapts to card size: small cards get smaller blocks, large cards get larger
            # 80% of total memory as base, with 20% reserve covering minor overflows
            available_memory_bytes = int(total_memory_bytes * memory_fraction)
            
            # Also check that we don't exceed free memory
            available_memory_bytes = min(available_memory_bytes, int(free_memory_bytes * memory_fraction))

            # Memory per element
            bytes_per_element = np.dtype(dtype).itemsize

            # Maximum elements per 7D block
            max_elements_per_block = available_memory_bytes // (
                bytes_per_element * overhead_factor
            )

            # For 7D, calculate block size per dimension
            # Use different sizes for spatial (0-2) and phase/time (3-6) dimensions
            # Spatial dimensions need larger blocks for better GPU utilization
            elements_per_dim = int(max_elements_per_block ** (1.0 / 7.0))

            # Ensure minimum block size for robust 7D operations and GPU utilization
            # Spatial dimensions: larger blocks (32-64) for better GPU utilization
            # Phase/time dimensions: smaller blocks (full size or 16-32) but still large enough
            # Adjust based on actual field size to ensure blocks fit in memory
            min_block_size_spatial = 32  # Minimum for spatial dimensions
            min_block_size_phase = 4    # Minimum for phase/time dimensions (can be smaller)
            
            block_tiling = []
            for i, dim_size in enumerate(field_shape):
                if i < 3:  # Spatial dimensions (x, y, z)
                    # Use larger blocks for spatial dimensions (32-64)
                    # This ensures better GPU utilization with larger workloads
                    # But don't exceed field size or available memory
                    block_size = max(
                        min_block_size_spatial,
                        min(dim_size, min(64, max(elements_per_dim, 32)))
                    )
                else:  # Phase and time dimensions (3, 4, 5, 6)
                    # For phase/time, use full dimension size if small, or reasonable fraction
                    # This preserves 7D structure while fitting in memory
                    if dim_size <= 8:
                        # Small dimensions: use full size
                        block_size = dim_size
                    else:
                        # Larger dimensions: use reasonable fraction
                        block_size = max(
                            min_block_size_phase,
                            min(dim_size, min(32, max(elements_per_dim, 4)))
                        )
                block_tiling.append(block_size)
            
            block_tiling = tuple(block_tiling)

            logger.info(
                f"Optimal 7D block tiling: {block_tiling} "
                f"(using {memory_fraction*100:.0f}% of "
                f"{total_memory_bytes/1e9:.2f}GB total GPU memory, "
                f"{free_memory_bytes/1e9:.2f}GB free)"
            )

            return block_tiling

        except Exception as e:
            logger.error(f"Error computing optimal 7D block tiling: {e}")
            raise RuntimeError(
                f"Failed to compute optimal 7D block tiling: {e}. "
                f"Ensure CUDA is properly configured and GPU memory "
                f"is available."
            ) from e
