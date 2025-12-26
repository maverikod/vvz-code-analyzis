"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D block tiling and memory management for electroweak coupling.

This module implements optimal 7D block tiling computation and memory
accounting for electroweak coupling computations in the BVP framework.

Physical Meaning:
    Calculates optimal block size per dimension for 7D space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring 80% GPU memory usage while
    preserving 7D geometric structure.

Mathematical Foundation:
    For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Available memory: 80% of free GPU memory
    - Block size per dimension: (available_memory / overhead) ^ (1/7)
    - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

Example:
    >>> tiling = ElectroweakBlockTiling()
    >>> optimal_tiling = tiling.compute_optimal_7d_block_tiling(field_shape)
"""

import numpy as np
from typing import Tuple
import logging

# CUDA optimization - GPU path when available
try:
    import cupy as cp

    CUDA_AVAILABLE = True
    logging.info("CUDA support enabled with CuPy")
except ImportError:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore
    logging.warning(
        "CUDA not available for electroweak coupling computation. "
        "Some features may be limited. Install cupy to enable GPU acceleration."
    )


class ElectroweakBlockTiling:
    """
    Optimal 7D block tiling and memory management for electroweak coupling.

    Physical Meaning:
        Calculates optimal block size per dimension for 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring 80% GPU memory usage while
        preserving 7D geometric structure with optimal memory access patterns.

    Mathematical Foundation:
        For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Available memory: 80% of free GPU memory
        - Block size per dimension: (available_memory / overhead) ^ (1/7)
        - Ensures blocks fit in GPU memory while preserving 7D structure
        - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

    Attributes:
        logger (logging.Logger): Logger instance.
    """

    def __init__(self) -> None:
        """
        Initialize block tiling calculator.

        Physical Meaning:
            Sets up the calculator for optimal 7D block tiling computation
            with GPU memory management.
        """
        self.logger = logging.getLogger(__name__)

        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

    def calculate_memory_requirement_7d(
        self, block_shape: Tuple[int, ...], overhead_factor: float = 10.0
    ) -> int:
        """
        Calculate memory requirement for a 7D block with explicit accounting.

        Physical Meaning:
            Calculates exact memory requirement in bytes for processing
            a 7D block of given shape, including all intermediate arrays
            for 7D space-time operations M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            For 7D block with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Base memory: N₀ × N₁ × ... × N₆ × bytes_per_element
            - Overhead accounts for: envelope + 3 phase components (sequential)
              + 7 gradients per component (7D) + gradient squares + currents (3 types)

        Args:
            block_shape (Tuple[int, ...]): Shape of the 7D block (must be 7D).
            overhead_factor (float): Memory overhead factor for operations.
                Accounts for: envelope + 3 phase components + 7 gradients per component
                + gradient squares + currents (3 types) = ~10x

        Returns:
            int: Required memory in bytes.

        Raises:
            ValueError: If block_shape is not 7D.
        """
        if len(block_shape) != 7:
            raise ValueError(
                f"Expected 7D block shape for memory calculation, "
                f"got {len(block_shape)}D. Shape: {block_shape}"
            )

        # Calculate total elements in 7D block
        total_elements = np.prod(block_shape)

        # Memory per element (complex128 = 16 bytes)
        bytes_per_element = 16

        # Total memory requirement with overhead
        memory_bytes = int(total_elements * bytes_per_element * overhead_factor)

        return memory_bytes

    def compute_optimal_7d_block_tiling(
        self, field_shape: Tuple[int, ...], overhead_factor: float = 10.0
    ) -> Tuple[int, ...]:
        """
        Compute optimal 7D block tiling for 80% GPU memory usage.

        Physical Meaning:
            Calculates optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring 80% GPU memory usage while
            preserving 7D geometric structure with optimal memory access patterns.

        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: 80% of free GPU memory
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Ensures blocks fit in GPU memory while preserving 7D structure
            - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

        Args:
            field_shape (Tuple[int, ...]): Shape of 7D field array
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
            overhead_factor (float): Memory overhead factor for operations
                (default: 10.0 for complex operations).

        Returns:
            Tuple[int, ...]: Optimal block tiling per dimension (7-tuple),
                ensuring each dimension has block size that fits in 80% GPU memory.

        Raises:
            ValueError: If field_shape is not 7D or memory calculation fails.
            RuntimeError: If GPU memory information is unavailable.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute optimal 7D block tiling")

        if len(field_shape) != 7:
            raise ValueError(
                f"Expected 7D field shape for optimal 7D block tiling, "
                f"got {len(field_shape)}D. Shape: {field_shape}"
            )

        try:
            # Get GPU memory info
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory_bytes = mem_info[0]

            # Use 80% of free memory as required
            available_memory_bytes = int(free_memory_bytes * 0.8)

            # Memory per element (complex128 = 16 bytes)
            bytes_per_element = 16

            # Maximum elements per 7D block
            max_elements_per_block = available_memory_bytes // (
                bytes_per_element * overhead_factor
            )

            # For 7D, calculate block size per dimension
            # 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            # - Spatial dimensions (0,1,2): ℝ³ₓ - typically larger, benefit from larger blocks
            # - Phase dimensions (3,4,5): 𝕋³_φ - periodic, moderate blocks optimal
            # - Temporal dimension (6): ℝₜ - sequential access pattern, smaller blocks
            elements_per_dim_base = max_elements_per_block ** (1.0 / 7.0)

            # Compute optimal block tiling per dimension with 7D geometry optimization
            block_tiling = []

            # Spatial dimensions (0,1,2): ℝ³ₓ
            # Use larger blocks (1.3x base) for better GPU memory coalescing
            spatial_factor = 1.3
            for dim_idx in range(3):
                dim_size = field_shape[dim_idx]
                block_size = max(8, min(int(elements_per_dim_base * spatial_factor), dim_size))
                # Round to nearest power of 2 for better GPU memory access (optional optimization)
                if block_size > 8:
                    log2_val = np.log2(block_size)
                    nearest_power = 2 ** int(log2_val + 0.5)
                    block_size = max(8, min(nearest_power, dim_size))
                block_tiling.append(block_size)

            # Phase dimensions (3,4,5): 𝕋³_φ
            # Use moderate blocks (1.0x base) for periodic boundary handling
            phase_factor = 1.0
            for dim_idx in range(3, 6):
                dim_size = field_shape[dim_idx]
                block_size = max(4, min(int(elements_per_dim_base * phase_factor), dim_size))
                block_tiling.append(block_size)

            # Temporal dimension (6): ℝₜ
            # Use smaller blocks (0.8x base) for sequential access patterns
            temporal_factor = 0.8
            dim_size = field_shape[6]
            block_size = max(4, min(int(elements_per_dim_base * temporal_factor), dim_size))
            block_tiling.append(block_size)

            block_tiling_tuple = tuple(block_tiling)

            self.logger.info(
                f"Optimal 7D block tiling: {block_tiling_tuple} "
                f"(using 80% of {free_memory_bytes/1e9:.2f}GB free GPU memory, "
                f"max {max_elements_per_block} elements)"
            )

            return block_tiling_tuple

        except Exception as e:
            self.logger.error(f"Failed to compute optimal 7D block tiling: {e}")
            raise RuntimeError(
                f"Cannot compute optimal 7D block tiling: {e}. "
                f"Ensure CUDA is properly configured and GPU memory is available."
            ) from e

    def get_available_gpu_memory(self) -> int:
        """
        Get available GPU memory (80% of free memory).

        Physical Meaning:
            Returns the amount of GPU memory available for block processing,
            calculated as 80% of free GPU memory to ensure safe operation.

        Returns:
            int: Available memory in bytes (80% of free GPU memory).

        Raises:
            RuntimeError: If GPU memory information is unavailable.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot get GPU memory")

        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory_bytes = mem_info[0]
            available_memory_bytes = int(free_memory_bytes * 0.8)
            return available_memory_bytes
        except Exception as e:
            self.logger.error(f"Failed to get GPU memory: {e}")
            raise RuntimeError(f"Cannot get GPU memory: {e}") from e

