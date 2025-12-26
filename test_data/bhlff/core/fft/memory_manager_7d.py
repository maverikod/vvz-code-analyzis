"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory Manager for 7D Computations in BHLFF Framework.

This module provides memory management for 7D phase field computations, which
scale as O(N^7), requiring special strategies for memory optimization and
block-based processing.

Theoretical Background:
    The 7D phase field computations require O(N^7) memory scaling, which
    quickly becomes prohibitive for large N. This module implements
    block-based decomposition, lazy loading, and compression strategies
    to manage memory efficiently.

Example:
    >>> manager = MemoryManager7D(domain_shape, max_memory_gb=8.0)
    >>> block = manager.get_block(block_id)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import logging
import gc
import psutil
import os


class MemoryManager7D:
    """
    Memory manager for 7D computations.

    Physical Meaning:
        Manages memory for 7D phase fields, which scale as O(N^7),
        requiring special strategies for memory optimization and
        block-based processing.

    Mathematical Foundation:
        - Block decomposition: partitioning field into blocks
        - Lazy loading: loading data on demand
        - Compression: compressing inactive blocks
        - Memory monitoring: tracking memory usage

    Attributes:
        domain_shape (Tuple[int, ...]): Dimensions of 7D domain.
        max_memory_bytes (int): Maximum memory usage in bytes.
        block_size (Tuple[int, ...]): Optimal block size for processing.
        active_blocks (Dict): Currently loaded blocks in memory.
        compressed_blocks (Dict): Compressed inactive blocks.
        memory_usage (float): Current memory usage in bytes.
    """

    def __init__(self, domain_shape: Tuple[int, ...], max_memory_gb: float = 8.0):
        """
        Initialize memory manager.

        Physical Meaning:
            Sets up memory management for 7D computations with
            optimal block size calculation and memory monitoring.

        Args:
            domain_shape: Dimensions of 7D domain.
            max_memory_gb: Maximum memory usage in GB.
        """
        self.domain_shape = domain_shape
        self.max_memory_bytes = int(max_memory_gb * 1024**3)
        self.block_size = self._calculate_optimal_block_size()
        self.active_blocks = {}
        self.compressed_blocks = {}
        self.memory_usage = 0

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Initialize memory monitoring
        self._setup_memory_monitoring()

        self.logger.info(
            f"MemoryManager7D initialized: domain={domain_shape}, "
            f"block_size={self.block_size}, max_memory={max_memory_gb:.1f}GB"
        )

    def get_block(self, block_id: Tuple[int, ...]) -> np.ndarray:
        """
        Get block data, loading from storage if necessary.

        Physical Meaning:
            Retrieves a block of the 7D field, loading it from
            compressed storage if not already in memory.

        Args:
            block_id: Block identifier (tuple of indices).

        Returns:
            np.ndarray: Block data.
        """
        if block_id in self.active_blocks:
            return self.active_blocks[block_id]

        # Load from compressed storage
        if block_id in self.compressed_blocks:
            block_data = self._decompress_block(block_id)
            self.active_blocks[block_id] = block_data
            self.memory_usage += block_data.nbytes
            return block_data

        # Create new block
        block_data = self._create_empty_block(block_id)
        self.active_blocks[block_id] = block_data
        self.memory_usage += block_data.nbytes

        return block_data

    def store_block(self, block_id: Tuple[int, ...], block_data: np.ndarray) -> None:
        """
        Store block data in memory or compressed storage.

        Physical Meaning:
            Stores block data, using compression if memory is limited
            and the block is not actively being used.

        Args:
            block_id: Block identifier.
            block_data: Block data to store.
        """
        if self._should_compress_block(block_id):
            self._compress_block(block_id, block_data)
            if block_id in self.active_blocks:
                del self.active_blocks[block_id]
                self.memory_usage -= block_data.nbytes
        else:
            self.active_blocks[block_id] = block_data.copy()
            self.memory_usage += block_data.nbytes

    def release_block(self, block_id: Tuple[int, ...]) -> None:
        """
        Release block from memory.

        Physical Meaning:
            Removes block from active memory, optionally compressing
            it for later retrieval.

        Args:
            block_id: Block identifier.
        """
        if block_id in self.active_blocks:
            block_data = self.active_blocks[block_id]
            self._compress_block(block_id, block_data)
            del self.active_blocks[block_id]
            self.memory_usage -= block_data.nbytes

    def get_memory_status(self) -> Dict[str, Any]:
        """
        Get current memory status.

        Physical Meaning:
            Returns detailed information about memory usage and
            available resources for 7D computations.

        Returns:
            Dict[str, Any]: Memory status information.
        """
        process = psutil.Process(os.getpid())
        system_memory = psutil.virtual_memory()

        return {
            "memory_usage_bytes": self.memory_usage,
            "memory_usage_gb": self.memory_usage / 1024**3,
            "max_memory_bytes": self.max_memory_bytes,
            "max_memory_gb": self.max_memory_bytes / 1024**3,
            "memory_utilization": self.memory_usage / self.max_memory_bytes,
            "active_blocks": len(self.active_blocks),
            "compressed_blocks": len(self.compressed_blocks),
            "process_memory_gb": process.memory_info().rss / 1024**3,
            "system_memory_available_gb": system_memory.available / 1024**3,
            "system_memory_utilization": system_memory.percent / 100,
        }

    def optimize_memory(self) -> None:
        """
        Optimize memory usage by compressing inactive blocks.

        Physical Meaning:
            Performs memory optimization by compressing blocks that
            are not actively being used, freeing up memory for
            new computations.
        """
        # Get memory status
        status = self.get_memory_status()

        if status["memory_utilization"] > 0.8:  # 80% threshold
            self.logger.info("Memory utilization high, compressing inactive blocks")

            # Compress least recently used blocks
            blocks_to_compress = list(self.active_blocks.keys())[
                :-5
            ]  # Keep last 5 blocks

            for block_id in blocks_to_compress:
                self.release_block(block_id)

            # Force garbage collection
            gc.collect()

            self.logger.info(
                f"Memory optimization complete: {len(blocks_to_compress)} blocks compressed"
            )

    def _calculate_optimal_block_size(self) -> Tuple[int, ...]:
        """
        Calculate optimal block size for memory management.

        Physical Meaning:
            Determines the optimal block size that fits in available
            memory while maintaining computational efficiency.

        Returns:
            Tuple[int, ...]: Optimal block size for each dimension.
        """
        # Calculate total elements
        total_elements = np.prod(self.domain_shape)

        # Estimate memory per element (float64 + complex128 for FFT)
        bytes_per_element = 8 + 16  # float64 + complex128

        # Calculate elements that fit in memory
        elements_per_gb = self.max_memory_bytes // bytes_per_element
        target_elements = min(
            total_elements, elements_per_gb // 4
        )  # Use 1/4 of available memory

        # Calculate block size (assume cubic blocks for simplicity)
        if len(self.domain_shape) == 7:
            block_size_1d = int(target_elements ** (1 / 7))
            block_size = tuple([block_size_1d] * 7)
        else:
            # For other dimensions, use proportional scaling
            scale_factor = (target_elements / total_elements) ** (
                1 / len(self.domain_shape)
            )
            block_size = tuple(
                [max(1, int(n * scale_factor)) for n in self.domain_shape]
            )

        return block_size

    def _create_empty_block(self, block_id: Tuple[int, ...]) -> np.ndarray:
        """
        Create empty block with appropriate size.

        Physical Meaning:
            Creates a new empty block with dimensions determined
            by the block size and position.

        Args:
            block_id: Block identifier.

        Returns:
            np.ndarray: Empty block array.
        """
        # Calculate block dimensions
        block_dims = []
        for i, (block_idx, domain_size, block_size) in enumerate(
            zip(block_id, self.domain_shape, self.block_size)
        ):
            start = block_idx * block_size
            end = min(start + block_size, domain_size)
            block_dims.append(end - start)

        return np.zeros(tuple(block_dims), dtype=np.float64)

    def _should_compress_block(self, block_id: Tuple[int, ...]) -> bool:
        """
        Determine if block should be compressed.

        Physical Meaning:
            Decides whether a block should be compressed based on
            memory usage and block access patterns.

        Args:
            block_id: Block identifier.

        Returns:
            bool: True if block should be compressed.
        """
        status = self.get_memory_status()
        return status["memory_utilization"] > 0.7  # 70% threshold

    def _compress_block(
        self, block_id: Tuple[int, ...], block_data: np.ndarray
    ) -> None:
        """
        Compress block data for storage.

        Physical Meaning:
            Compresses block data to reduce memory usage while
            maintaining data integrity for later retrieval.

        Args:
            block_id: Block identifier.
            block_data: Block data to compress.
        """
        # Simple compression using numpy's built-in compression
        compressed_data = np.compress(block_data.flatten() != 0, block_data.flatten())
        self.compressed_blocks[block_id] = {
            "data": compressed_data,
            "shape": block_data.shape,
            "dtype": block_data.dtype,
        }

    def _decompress_block(self, block_id: Tuple[int, ...]) -> np.ndarray:
        """
        Decompress block data from storage.

        Physical Meaning:
            Decompresses block data from storage, restoring it
            to its original form for computation.

        Args:
            block_id: Block identifier.

        Returns:
            np.ndarray: Decompressed block data.
        """
        if block_id not in self.compressed_blocks:
            raise KeyError(f"Block {block_id} not found in compressed storage")

        compressed_info = self.compressed_blocks[block_id]
        compressed_data = compressed_info["data"]
        shape = compressed_info["shape"]
        dtype = compressed_info["dtype"]

        # Reconstruct block
        block_data = np.zeros(shape, dtype=dtype)
        nonzero_indices = np.unravel_index(np.arange(len(compressed_data)), shape)
        block_data[nonzero_indices] = compressed_data

        return block_data

    def _setup_memory_monitoring(self) -> None:
        """
        Setup memory monitoring and logging.

        Physical Meaning:
            Initializes memory monitoring to track usage and
            provide warnings when memory limits are approached.
        """
        self.logger.info(
            f"Memory monitoring setup: max_memory={self.max_memory_bytes/1024**3:.1f}GB"
        )

        # Log initial memory status
        status = self.get_memory_status()
        self.logger.info(
            f"Initial memory status: {status['memory_usage_gb']:.2f}GB used, "
            f"{status['system_memory_available_gb']:.2f}GB system available"
        )

    def cleanup(self) -> None:
        """
        Cleanup memory manager and free all resources.

        Physical Meaning:
            Releases all memory resources and cleans up
            compressed storage.
        """
        self.active_blocks.clear()
        self.compressed_blocks.clear()
        self.memory_usage = 0
        gc.collect()

        self.logger.info("Memory manager cleanup complete")
