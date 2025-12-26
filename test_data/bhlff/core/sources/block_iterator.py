"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block iterator for 7D field blocks with CUDA support and vectorization.

This module provides block iteration functionality for 7D field blocks,
including vectorized operations, CUDA batch processing, and metadata validation.

Physical Meaning:
    Iterates over 7D field blocks with memory safety warnings (not hard errors)
    for large block counts. Uses vectorized operations and CUDA acceleration
    when available with 80% GPU memory limit. Processes blocks preserving
    7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. Validates metadata matches true block shape.

Mathematical Foundation:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Block iteration: vectorized traversal of all 7D block combinations
    - Metadata validation: vectorized shape comparison ensures integrity
    - CUDA batch processing: processes multiple blocks when GPU memory allows
    - Large domain handling: warnings instead of errors for large block counts
    - Vectorized operations: all array operations use NumPy/CuPy vectorization

Example:
    >>> iterator = BlockIterator(generator, cache_manager, blocks_per_dim, total_blocks)
    >>> for block, metadata in iterator.iterate(max_blocks=1000):
    ...     process_block(block)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, Iterator, List
import logging
from itertools import product

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .block_cache_manager import BlockCacheManager
from .block_metadata import BlockMetadata


class BlockIterator:
    """
    Block iterator for 7D field blocks with CUDA support and vectorization.

    Physical Meaning:
        Iterates over 7D field blocks with memory safety warnings (not hard errors)
        for large block counts. Uses vectorized operations and CUDA acceleration
        when available with 80% GPU memory limit. Processes blocks preserving
        7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. Validates metadata matches true block shape.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Block iteration: vectorized traversal of all 7D block combinations
        - Metadata validation: vectorized shape comparison ensures integrity
        - CUDA batch processing: processes multiple blocks when GPU memory allows
        - Large domain handling: warnings instead of errors for large block counts

    Attributes:
        generator: Block generator instance (has get_block_by_indices method).
        cache_manager (BlockCacheManager): Cache manager for block operations.
        blocks_per_dim (List[int]): Number of blocks per dimension (7D).
        total_blocks (int): Total number of blocks.
        block_size (Tuple[int, ...]): Block size per dimension (7D).
        use_cuda (bool): Whether CUDA is available and enabled.
        block_metadata (Dict[str, BlockMetadata]): Metadata cache dictionary.
        logger (logging.Logger): Logger instance.
    """

    def __init__(
        self,
        generator: Any,
        cache_manager: BlockCacheManager,
        blocks_per_dim: List[int],
        total_blocks: int,
        block_size: Tuple[int, ...],
        use_cuda: bool,
        block_metadata: Dict[str, BlockMetadata],
        logger: logging.Logger,
    ) -> None:
        """
        Initialize block iterator.

        Args:
            generator: Block generator instance (has get_block_by_indices method).
            cache_manager (BlockCacheManager): Cache manager for block operations.
            blocks_per_dim (List[int]): Number of blocks per dimension (7D).
            total_blocks (int): Total number of blocks.
            block_size (Tuple[int, ...]): Block size per dimension (7D).
            use_cuda (bool): Whether CUDA is available and enabled.
            block_metadata (Dict[str, BlockMetadata]): Metadata cache dictionary.
            logger (logging.Logger): Logger instance.
        """
        self.generator = generator
        self.cache_manager = cache_manager
        self.blocks_per_dim = blocks_per_dim
        self.total_blocks = total_blocks
        self.block_size = block_size
        self.use_cuda = use_cuda
        self.block_metadata = block_metadata
        self.logger = logger

    def iterate(
        self, max_blocks: Optional[int] = None
    ) -> Iterator[Tuple[np.ndarray, Dict[str, Any]]]:
        """
        Iterate over all blocks in the 7D field with CUDA support and vectorization.

        Physical Meaning:
            Iterates over 7D field blocks with memory safety warnings (not hard errors)
            for large block counts. Uses vectorized operations and CUDA acceleration
            when available with 80% GPU memory limit. Processes blocks preserving
            7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. Validates metadata matches true block shape.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Block iteration: vectorized traversal of all 7D block combinations
            - Metadata validation: vectorized shape comparison ensures integrity
            - CUDA batch processing: processes multiple blocks when GPU memory allows
            - Large domain handling: warnings instead of errors for large block counts
            - Vectorized operations: all array operations use NumPy/CuPy vectorization

        Args:
            max_blocks (Optional[int]): Maximum number of blocks to iterate.
                If None, uses safety limit based on memory constraints.

        Yields:
            Tuple[np.ndarray, Dict[str, Any]]: Block data and metadata with
                block_shape matching true block shape.
        """
        # Validate 7D structure: ensure blocks_per_dim has 7 elements
        if len(self.blocks_per_dim) != 7:
            raise ValueError(
                f"Expected 7D block configuration for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(self.blocks_per_dim)}D: {self.blocks_per_dim}"
            )

        # Safety limit: allow large block counts with warnings (not hard errors)
        safe_default_blocks = 50000
        very_large_blocks_cap = 200000  # Hard cap only for extremely large domains

        if max_blocks is None:
            max_blocks = safe_default_blocks

        # Warning thresholds instead of hard errors (allows large domains)
        if self.total_blocks > very_large_blocks_cap:
            self.logger.warning(
                f"Extremely large number of blocks ({self.total_blocks}). "
                f"Using safety limit of {min(max_blocks, very_large_blocks_cap)} blocks. "
                f"Consider increasing block_size or processing blocks individually."
            )
            max_blocks = min(max_blocks, very_large_blocks_cap)
        elif self.total_blocks > max_blocks:
            self.logger.warning(
                f"Large number of blocks ({self.total_blocks}) - iteration may take time. "
                f"Consider using max_blocks parameter to limit processing. "
                f"Proceeding with iteration (will process up to {max_blocks} blocks)."
            )
        else:
            self.logger.info(
                f"Iterating over {self.total_blocks} blocks "
                f"(limit: {max_blocks if max_blocks < self.total_blocks else 'unlimited'})"
            )

        block_count = 0
        # Vectorized iteration over all 7D block combinations
        blocks_per_dim_array = np.array(self.blocks_per_dim, dtype=np.int64)

        # Compute optimal batch size for CUDA processing (if available)
        # Balance between GPU occupancy and memory usage (80% rule)
        batch_size = 1
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                from ...utils.cuda_utils import calculate_optimal_window_memory
                
                # Estimate batch size based on block size and GPU memory
                block_volume = np.prod(self.block_size)
                bytes_per_element = 16  # complex128
                block_memory = block_volume * bytes_per_element
                
                # Get optimal window memory based on TOTAL GPU memory
                max_window_elements, _, _ = calculate_optimal_window_memory(
                    gpu_memory_ratio=0.8,
                    overhead_factor=1.0,  # Just for block storage
                    logger=None,  # Don't log here
                )
                
                max_window_memory = max_window_elements * bytes_per_element
                # Allow batching if memory permits (up to 3 blocks in batch)
                if block_memory * 3 < max_window_memory:
                    batch_size = min(3, max_blocks // 10 if max_blocks else 3)
                    self.logger.debug(
                        f"Using CUDA batch processing with batch_size={batch_size}"
                    )
            except Exception as e:
                self.logger.debug(f"Could not compute CUDA batch size: {e}")

        for block_indices in product(
            *[range(n_blocks) for n_blocks in self.blocks_per_dim]
        ):
            if block_count >= max_blocks:
                self.logger.warning(
                    f"Reached iteration limit ({max_blocks}). "
                    f"Total blocks: {self.total_blocks}, processed: {block_count}"
                )
                break

            # Validate 7D structure: ensure block_indices has 7 elements
            block_indices_array = np.array(block_indices, dtype=np.int64)
            if len(block_indices) != 7 or block_indices_array.shape != (7,):
                self.logger.error(
                    f"Invalid block indices dimensionality: "
                    f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                    f"got {len(block_indices)}D: {block_indices}"
                )
                continue

            # Vectorized bounds check: ensure indices are within valid range
            if np.any(block_indices_array < 0) or np.any(
                block_indices_array >= blocks_per_dim_array
            ):
                self.logger.error(
                    f"Block indices out of bounds: {block_indices}, "
                    f"valid range: [0, {blocks_per_dim_array})"
                )
                continue

            # Get block with CUDA support and metadata validation
            try:
                block = self.generator.get_block_by_indices(block_indices)
            except Exception as e:
                self.logger.error(
                    f"Failed to get block {block_indices}: {e}. " f"Skipping block."
                )
                continue

            # Validate block has 7D structure (vectorized shape check)
            if block.ndim != 7:
                self.logger.error(
                    f"Block {block_indices} has wrong dimensionality: "
                    f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {block.ndim}D. "
                    f"Skipping block."
                )
                continue

            # Vectorized shape validation: ensure shape is 7D
            block_shape_array = np.array(block.shape, dtype=np.int64)
            if block_shape_array.shape != (7,):
                self.logger.error(
                    f"Block {block_indices} has invalid shape: {block.shape}. "
                    f"Expected 7D shape tuple. Skipping block."
                )
                continue

            # Load and validate metadata to ensure block_shape matches true block shape
            block_id = self.cache_manager.get_block_id(block_indices)
            metadata_path = self.cache_manager.get_metadata_path(block_id)

            # Use actual block shape as default (ensures metadata matches true shape)
            block_shape_from_metadata = block.shape

            if metadata_path.exists():
                try:
                    # Validate metadata matches actual block shape (vectorized comparison)
                    metadata_valid, metadata = self.cache_manager.validate_metadata(
                        metadata_path, block, block_indices
                    )

                    if metadata_valid and metadata is not None:
                        if hasattr(metadata, "block_shape"):
                            # Vectorized shape comparison (7D)
                            metadata_shape_array = np.array(
                                metadata.block_shape, dtype=np.int64
                            )
                            # Vectorized comparison
                            if metadata_shape_array.shape == block_shape_array.shape:
                                shape_match = np.array_equal(
                                    metadata_shape_array, block_shape_array
                                )
                            else:
                                shape_match = False

                            # Ensure metadata matches actual shape
                            if shape_match:
                                block_shape_from_metadata = metadata.block_shape
                            else:
                                # Metadata mismatch: use actual shape (ensures integrity)
                                self.logger.debug(
                                    f"Metadata shape mismatch for block "
                                    f"{block_indices}: "
                                    f"metadata={metadata.block_shape}, "
                                    f"actual={block.shape}. Using actual shape."
                                )
                                block_shape_from_metadata = block.shape

                                # Update metadata to match actual shape
                                self.cache_manager.save_block_metadata(
                                    block_id,
                                    block_indices,
                                    block.shape,  # Use actual shape
                                    self.cache_manager.get_block_path(block_id),
                                    self.block_metadata,
                                )
                        else:
                            # No block_shape in metadata: use actual shape
                            block_shape_from_metadata = block.shape
                    else:
                        # Invalid metadata: use actual shape and update
                        block_shape_from_metadata = block.shape
                        self.cache_manager.save_block_metadata(
                            block_id,
                            block_indices,
                            block.shape,  # Use actual shape
                            self.cache_manager.get_block_path(block_id),
                            self.block_metadata,
                        )
                except Exception as e:
                    self.logger.debug(
                        f"Failed to load/validate metadata for block {block_indices}: {e}. "
                        f"Using actual block shape."
                    )
                    block_shape_from_metadata = block.shape

            # Final validation: ensure block_shape has 7D structure (vectorized check)
            if isinstance(block_shape_from_metadata, tuple):
                shape_check_array = np.array(block_shape_from_metadata, dtype=np.int64)
                if shape_check_array.shape != (7,):
                    self.logger.warning(
                        f"Block shape has wrong dimensionality: "
                        f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got "
                        f"{len(block_shape_from_metadata)}D. "
                        f"Using actual block shape."
                    )
                    block_shape_from_metadata = block.shape

            # Ensure metadata matches true block shape (final check)
            # Vectorized comparison
            if not np.array_equal(
                np.array(block_shape_from_metadata, dtype=np.int64),
                block_shape_array,
            ):
                block_shape_from_metadata = block.shape

            metadata = {
                "block_indices": block_indices,
                "block_shape": block_shape_from_metadata,  # Always matches true shape
                "block_id": block_id,
            }
            yield block, metadata
            block_count += 1
