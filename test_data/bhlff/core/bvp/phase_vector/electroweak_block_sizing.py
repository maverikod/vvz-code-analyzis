"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D block size calculation from GPU memory for electroweak coupling.

This module implements optimal 7D block size calculation based on
80% GPU memory with explicit accounting and OOM protection.

Physical Meaning:
    Calculates optimal block size per dimension for 7D space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ based on 80% of free GPU memory, ensuring
    proper memory accounting and OOM protection.

Mathematical Foundation:
    For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Available memory: 80% of free GPU memory
    - Block size per dimension: (available_memory / overhead) ^ (1/7)
    - Ensures blocks fit in GPU memory while preserving 7D structure
    - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

Example:
    >>> from bhlff.core.bvp.phase_vector.block_tiling import ElectroweakBlockTiling
    >>> tiling = ElectroweakBlockTiling()
    >>> block_sizing = ElectroweakBlockSizing(tiling)
    >>> optimal_size = block_sizing.compute_optimal_block_size_from_gpu_memory(field_shape)
"""

import numpy as np
from typing import Tuple
import logging

from bhlff.core.bvp.phase_vector.block_tiling import ElectroweakBlockTiling

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


class ElectroweakBlockSizing:
    """
    Optimal 7D block size calculation from GPU memory.

    Physical Meaning:
        Calculates optimal block size per dimension for 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ based on 80% of free GPU memory, ensuring
        proper memory accounting and OOM protection.

    Mathematical Foundation:
        For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Available memory: 80% of free GPU memory
        - Block size per dimension: (available_memory / overhead) ^ (1/7)
        - Ensures blocks fit in GPU memory while preserving 7D structure
        - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

    Attributes:
        block_tiling (ElectroweakBlockTiling): Block tiling calculator.
        logger (logging.Logger): Logger instance.
    """

    def __init__(self, block_tiling: ElectroweakBlockTiling) -> None:
        """
        Initialize block sizing calculator.

        Physical Meaning:
            Sets up the calculator for optimal 7D block size computation
            based on GPU memory with explicit accounting.

        Args:
            block_tiling (ElectroweakBlockTiling): Block tiling calculator.
        """
        self.block_tiling = block_tiling
        self.logger = logging.getLogger(__name__)

        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

    def compute_optimal_block_size_from_gpu_memory(
        self, field_shape: Tuple[int, ...], overhead_factor: float = 10.0
    ) -> Tuple[int, ...]:
        """
        Compute optimal 7D block size from GPU memory with explicit accounting.

        Physical Meaning:
            Calculates optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ based on 80% of free GPU memory, ensuring
            proper memory accounting and OOM protection.

        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: 80% of free GPU memory
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Ensures blocks fit in GPU memory while preserving 7D structure
            - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

        Args:
            field_shape (Tuple[int, ...]): Shape of 7D field array (must be 7D).
            overhead_factor (float): Memory overhead factor for operations (default: 10.0).

        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple).

        Raises:
            RuntimeError: If CUDA is not available or memory calculation fails.
            ValueError: If field_shape is not 7D.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute optimal block size")

        if len(field_shape) != 7:
            raise ValueError(
                f"Expected 7D field shape, got {len(field_shape)}D. Shape: {field_shape}"
            )

        # Get available GPU memory (80% of free)
        available_memory = self.block_tiling.get_available_gpu_memory()

        # Memory per element (complex128 = 16 bytes)
        bytes_per_element = 16

        # Maximum elements per 7D block
        max_elements_per_block = available_memory // (bytes_per_element * overhead_factor)

        if max_elements_per_block < 1:
            raise RuntimeError(
                f"GPU memory too small: {available_memory/1e9:.2f}GB available, "
                f"need at least {bytes_per_element * overhead_factor/1e9:.2f}GB per element"
            )

        # Calculate base block size per dimension (7D geometry)
        elements_per_dim_base = max_elements_per_block ** (1.0 / 7.0)

        # Compute optimal block tiling per dimension with 7D geometry optimization
        block_tiling = []

        # Spatial dimensions (0,1,2): ℝ³ₓ - use larger blocks (1.3x base)
        spatial_factor = 1.3
        for dim_idx in range(3):
            dim_size = field_shape[dim_idx]
            block_size = max(8, min(int(elements_per_dim_base * spatial_factor), dim_size))
            # Round to nearest power of 2 for better GPU memory access
            if block_size > 8:
                log2_val = np.log2(block_size)
                nearest_power = 2 ** int(log2_val + 0.5)
                block_size = max(8, min(nearest_power, dim_size))
            block_tiling.append(block_size)

        # Phase dimensions (3,4,5): 𝕋³_φ - use moderate blocks (1.0x base)
        phase_factor = 1.0
        for dim_idx in range(3, 6):
            dim_size = field_shape[dim_idx]
            block_size = max(4, min(int(elements_per_dim_base * phase_factor), dim_size))
            block_tiling.append(block_size)

        # Temporal dimension (6): ℝₜ - use smaller blocks (0.8x base)
        temporal_factor = 0.8
        dim_size = field_shape[6]
        block_size = max(4, min(int(elements_per_dim_base * temporal_factor), dim_size))
        block_tiling.append(block_size)

        block_tiling_tuple = tuple(block_tiling)

        self.logger.info(
            f"Optimal 7D block size from GPU memory: {block_tiling_tuple} "
            f"(using 80% of {available_memory/1e9:.2f}GB free GPU memory, "
            f"max {max_elements_per_block} elements)"
        )

        return block_tiling_tuple

