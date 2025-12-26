"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimal block tiling computation for 7D admittance processing on GPU.

This module provides optimal 7D block tiling computation for GPU memory
management, ensuring 80% GPU memory usage while preserving 7D geometric
structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    Calculates optimal block size per dimension for 7D space-time processing,
    ensuring efficient GPU memory usage (80%) while preserving 7D geometric
    structure throughout block-based computations.

Mathematical Foundation:
    For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Available memory: 80% of free GPU memory
    - Block size per dimension: (available_memory / overhead) ^ (1/7)
    - Ensures blocks fit in GPU memory while preserving 7D structure

Example:
    >>> optimizer = AdmittanceOptimization()
    >>> block_tiling = optimizer.compute_optimal_7d_block_tiling(field_gpu)
"""

import logging
import numpy as np
from typing import Tuple

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class AdmittanceOptimization:
    """
    Optimal block tiling computation for 7D admittance processing.

    Physical Meaning:
        Calculates optimal block size per dimension for 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring 80% GPU memory usage while
        preserving 7D geometric structure.

    Mathematical Foundation:
        For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Available memory: 80% of free GPU memory
        - Block size per dimension: (available_memory / overhead) ^ (1/7)
        - Ensures blocks fit in GPU memory while preserving 7D structure

    Attributes:
        logger (logging.Logger): Logger instance.
    """

    def __init__(self):
        """
        Initialize optimization operations.

        Physical Meaning:
            Sets up optimization operations for computing optimal 7D block tiling
            that uses 80% of GPU memory while preserving geometric structure.
        """
        self.logger = logging.getLogger(__name__)

    def compute_optimal_7d_block_tiling(
        self, field_gpu: "cp.ndarray"
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
            field_gpu (cp.ndarray): 7D field array on GPU with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆).

        Returns:
            Tuple[int, ...]: Optimal block tiling per dimension (7-tuple),
                ensuring each dimension has block size that fits in 80% GPU memory.

        Raises:
            ValueError: If field is not 7D or memory calculation fails.
        """
        # Verify 7D structure
        if field_gpu.ndim != 7:
            raise ValueError(
                f"Expected 7D field for optimal 7D block tiling, "
                f"got {field_gpu.ndim}D. Shape: {field_gpu.shape}"
            )

        # Get GPU memory info
        mem_info = cp.cuda.runtime.memGetInfo()
        free_memory_bytes = mem_info[0]

        # Use 80% of free memory as required
        available_memory_bytes = int(free_memory_bytes * 0.8)

        # Memory per element (complex128 = 16 bytes)
        bytes_per_element = 16

        # Memory overhead for admittance computation with 7D geometry:
        # - Input field: 1x
        # - Source field: 1x
        # - Field amplitude squared: 1x
        # - Correlation: 1x
        # - Frequency-dependent phase factors: 1x
        # - Intermediate operations: 2x
        # - Reduction buffers: 1x
        # - FFT workspace (if needed for 7D operations): 2x
        # - Stream synchronization buffers: 1x
        # Total: ~10x (optimized for 7D operations with vectorization)
        overhead_factor = 10

        # Maximum elements per 7D block
        max_elements_per_block = available_memory_bytes // (
            bytes_per_element * overhead_factor
        )

        # Get field shape for 7D geometry optimization
        shape = field_gpu.shape

        # For 7D array, calculate optimal block tiling considering 7D structure
        # 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        # - Spatial dimensions (0,1,2): ℝ³ₓ - typically larger, benefit from larger blocks
        # - Phase dimensions (3,4,5): 𝕋³_φ - periodic, moderate blocks optimal
        # - Temporal dimension (6): ℝₜ - sequential access pattern, smaller blocks
        # Compute base block size per dimension: (max_elements)^(1/7)
        # This ensures the 7D block volume fits in available memory
        elements_per_dim_base = max_elements_per_block ** (1.0 / 7.0)

        # Compute optimal block tiling per dimension with 7D geometry optimization
        # Group dimensions by type for optimal memory access patterns:
        # - Spatial group (0,1,2): larger blocks for better cache locality and coalescing
        # - Phase group (3,4,5): moderate blocks for periodic boundary handling
        # - Temporal group (6): smaller blocks for sequential access patterns
        block_tiling = []
        
        # Spatial dimensions (0,1,2): ℝ³ₓ
        # Use larger blocks (1.3x base) for better GPU memory coalescing
        # Spatial dimensions are typically contiguous in memory and benefit from larger blocks
        spatial_factor = 1.3
        for dim_idx in range(3):
            dim_size = shape[dim_idx]
            block_size = max(8, min(int(elements_per_dim_base * spatial_factor), dim_size))
            # Round to nearest power of 2 for better GPU memory access (optional optimization)
            # This improves memory coalescing on GPU
            if block_size > 8:
                # Round to nearest power of 2 for better GPU coalescing
                log2_val = np.log2(block_size)
                nearest_power = 2 ** int(log2_val + 0.5)
                block_size = max(8, min(nearest_power, dim_size))
            block_tiling.append(block_size)
        
        # Phase dimensions (3,4,5): 𝕋³_φ
        # Use moderate blocks (1.0x base) for periodic boundary conditions
        # Phase dimensions are periodic and moderate blocks work well
        phase_factor = 1.0
        for dim_idx in range(3, 6):
            dim_size = shape[dim_idx]
            block_size = max(4, min(int(elements_per_dim_base * phase_factor), dim_size))
            block_tiling.append(block_size)
        
        # Temporal dimension (6): ℝₜ
        # Use smaller blocks (0.7x base) for sequential access patterns
        # Temporal dimension benefits from smaller blocks for cache efficiency
        temporal_factor = 0.7
        dim_size = shape[6]
        block_size = max(4, min(int(elements_per_dim_base * temporal_factor), dim_size))
        block_tiling.append(block_size)
        
        block_tiling = tuple(block_tiling)

        # Verify block tiling is valid (each dimension should be at least 4)
        if any(block_size < 4 for block_size in block_tiling):
            self.logger.warning(
                f"Some block sizes are too small: {block_tiling}. "
                f"Adjusting to minimum size 4."
            )
            block_tiling = tuple(max(4, block_size) for block_size in block_tiling)

        # Verify total block memory fits
        block_volume = 1
        for block_size in block_tiling:
            block_volume *= block_size
        block_memory = block_volume * bytes_per_element * overhead_factor

        if block_memory > available_memory_bytes:
            self.logger.warning(
                f"Block memory {block_memory/1e9:.2f}GB exceeds available "
                f"{available_memory_bytes/1e9:.2f}GB. Reducing block sizes."
            )
            # Reduce block sizes proportionally while preserving 7D geometry ratios
            scale_factor = (available_memory_bytes / block_memory) ** (1.0 / 7.0)
            # Preserve relative sizes for spatial/phase/temporal dimensions
            block_tiling = tuple(
                max(4, int(block_size * scale_factor)) for block_size in block_tiling
            )
            # Recompute block memory to verify
            block_volume = 1
            for block_size in block_tiling:
                block_volume *= block_size
            block_memory = block_volume * bytes_per_element * overhead_factor

        # Final verification: ensure block fits in 80% of available memory
        if block_memory > available_memory_bytes:
            self.logger.warning(
                f"After adjustment, block memory {block_memory/1e9:.2f}GB still exceeds "
                f"available {available_memory_bytes/1e9:.2f}GB. Using minimum block sizes."
            )
            # Use minimum safe block sizes
            block_tiling = tuple(max(4, min(16, dim_size)) for dim_size in shape)

        self.logger.info(
            f"Optimal 7D block tiling: {block_tiling} "
            f"(available GPU memory: {available_memory_bytes / 1e9:.2f} GB, using 80%, "
            f"block volume: {block_volume} elements)"
        )

        return block_tiling
