"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block configuration calculator for 7D domains.

This module provides functionality for computing optimal block sizes and
block configurations for 7D space-time domains with CUDA support.

Physical Meaning:
    Calculates optimal block sizes and block configurations for 7D space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring efficient memory usage with 80% GPU limit
    and allowing large block counts with warnings instead of hard errors.

Mathematical Foundation:
    For 7D blocks with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Available memory: 80% of free GPU memory (if CUDA) or max_memory_mb
    - Block size per dimension: (available_memory / overhead) ^ (1/7)
    - Blocks per dimension: (domain_size + block_size - 1) // block_size
    - Total blocks: ∏ᵢ₌₀⁶ (blocks_per_dim[i])

Example:
    >>> config = BlockConfig(domain, logger, use_cuda)
    >>> block_size = config.compute_optimal_block_size(max_memory_mb)
    >>> blocks_per_dim, total_blocks = config.compute_block_configuration(
    ...     block_size
    ... )
"""

import numpy as np
import logging
from typing import Tuple, List

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..domain import Domain
from ..domain.optimal_block_size_calculator import OptimalBlockSizeCalculator


class BlockConfig:
    """
    Block configuration calculator for 7D domains.

    Physical Meaning:
        Computes optimal block sizes and block configurations for 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring efficient memory usage with 80% GPU limit
        and allowing large block counts with warnings instead of hard errors.

    Mathematical Foundation:
        For 7D blocks:
        - Block size calculation: (available_memory / overhead) ^ (1/7)
        - Block configuration: number of blocks per dimension
        - Total blocks: product of blocks per dimension

    Attributes:
        domain (Domain): Computational domain.
        logger (logging.Logger): Logger instance.
        use_cuda (bool): Whether CUDA is available and enabled.
    """

    def __init__(self, domain: Domain, logger: logging.Logger, use_cuda: bool) -> None:
        """
        Initialize block configuration calculator.

        Args:
            domain (Domain): Computational domain.
            logger (logging.Logger): Logger instance.
            use_cuda (bool): Whether CUDA is available and enabled.
        """
        self.domain = domain
        self.logger = logger
        self.use_cuda = use_cuda
        
        # Initialize unified block size calculator
        self._block_size_calculator = OptimalBlockSizeCalculator(
            gpu_memory_ratio=0.8  # Use 80% GPU memory (project requirement)
        )

    def compute_optimal_block_size(self, max_memory_mb: float) -> Tuple[int, ...]:
        """
        Compute optimal block size based on memory constraints with CUDA support.

        Physical Meaning:
            Calculates block size that fits within memory constraints (80% GPU
            memory limit if CUDA available) while maximizing processing efficiency
            for 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. Uses unified
            OptimalBlockSizeCalculator for consistent calculation.

        Mathematical Foundation:
            For 7D blocks with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: 80% of free GPU memory (if CUDA) or max_memory_mb
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Preserves 7D structure: spatial (0,1,2), phase (3,4,5), temporal (6)

        Args:
            max_memory_mb (float): Maximum memory in MB (CPU fallback).

        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple).
        """
        # Use unified block size calculator
        try:
            block_tiling = self._block_size_calculator.calculate_for_7d(
                domain_shape=self.domain.shape,
                dtype=np.complex128,
                overhead_factor=5.0,  # Memory overhead for operations
            )
            
            self.logger.info(
                f"Optimal block size (via unified calculator): {block_tiling} "
                f"(max memory: {max_memory_mb} MB, GPU memory ratio: 80%)"
            )
            
            return block_tiling
        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size with unified calculator: {e}, "
                f"falling back to legacy calculation"
            )
            # Fallback to legacy calculation
            return self._compute_optimal_block_size_legacy(max_memory_mb)
    
    def _compute_optimal_block_size_legacy(self, max_memory_mb: float) -> Tuple[int, ...]:
        """
        Legacy block size calculation (fallback).
        
        Physical Meaning:
            Legacy calculation method used as fallback when unified
            calculator fails.
            
        Args:
            max_memory_mb (float): Maximum memory in MB.
            
        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple).
        """
        # Memory per element (complex128 = 16 bytes)
        bytes_per_element = 16
        overhead_factor = 5.0  # Memory overhead for operations

        # Try CUDA if available and enabled
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                from ...utils.cuda_utils import calculate_optimal_window_memory
                max_window_elements, _, _ = calculate_optimal_window_memory(
                    gpu_memory_ratio=0.8,
                    overhead_factor=overhead_factor,
                    logger=self.logger,
                )
                max_elements = max_window_elements
            except Exception as e:
                self.logger.warning(
                    f"Failed to get GPU memory info: {e}, using CPU fallback"
                )
                max_elements = (max_memory_mb * 1024 * 1024) / bytes_per_element
        else:
            max_elements = (max_memory_mb * 1024 * 1024) / bytes_per_element

        # For 7D, compute block size per dimension
        # Assuming roughly equal dimensions
        elements_per_dim = int(max_elements ** (1.0 / 7.0))

        # Ensure reasonable bounds (4 to domain size)
        block_size_per_dim = max(4, min(elements_per_dim, 128))

        # Create block size tuple (7D: spatial, phase, temporal)
        block_size = tuple(
            min(block_size_per_dim, dim_size) for dim_size in self.domain.shape
        )

        self.logger.info(
            f"Optimal block size (legacy): {block_size} "
            f"(max memory: {max_memory_mb} MB, "
            f"max elements: {max_elements:.0e}, "
            f"elements per dim: {elements_per_dim})"
        )

        return block_size

    def compute_block_configuration(
        self, block_size: Tuple[int, ...]
    ) -> Tuple[List[int], int]:
        """
        Compute block configuration for the 7D domain.

        Physical Meaning:
            Calculates number of blocks per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, allowing large block counts with warnings
            instead of hard errors.

        Args:
            block_size (Tuple[int, ...]): Block size per dimension (7-tuple).

        Returns:
            Tuple[List[int], int]: (blocks_per_dim, total_blocks).
        """
        blocks_per_dim = []
        for dim_size, block_dim_size in zip(self.domain.shape, block_size):
            n_blocks = (dim_size + block_dim_size - 1) // block_dim_size
            blocks_per_dim.append(n_blocks)

        # Safe computation: use int64 to avoid overflow
        try:
            blocks_array = np.array(blocks_per_dim, dtype=np.int64)
            total_blocks = int(np.prod(blocks_array))
        except (OverflowError, ValueError) as e:
            self.logger.warning(
                f"Error computing total blocks: {e}. "
                f"Blocks per dim: {blocks_per_dim}. "
                f"Using safe limit."
            )
            # Use safe limit instead of hard error
            total_blocks = 100000

        # Warning thresholds instead of hard limits
        # Allow large block counts with warnings, not hard errors
        max_safe_blocks = 50000
        very_large_blocks = 200000  # Hard cap only for extremely large domains

        if total_blocks > very_large_blocks:
            self.logger.warning(
                f"Extremely large number of blocks ({total_blocks}). "
                f"This may cause system issues. "
                f"Consider increasing block_size. Current limit: {very_large_blocks}."
            )
            # Cap only at extremely large values
            total_blocks = min(total_blocks, very_large_blocks)
        elif total_blocks > max_safe_blocks:
            self.logger.warning(
                f"Large number of blocks ({total_blocks}). "
                f"Iteration may take time. "
                f"Consider increasing block_size for better performance."
            )
            # Don't limit here, just warn

        self.logger.info(
            f"Block configuration: {blocks_per_dim} blocks per dimension, "
            f"total {total_blocks} blocks"
        )

        return blocks_per_dim, total_blocks
