"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized block processor for 7D domain operations.

This module implements CUDA-accelerated block processing for 7D domains
to handle memory-efficient computations on large 7D space-time grids.

Physical Meaning:
    Provides CUDA-accelerated block processing for 7D phase field computations,
    enabling memory-efficient operations on large 7D space-time domains
    using GPU acceleration for maximum performance.

Example:
    >>> processor = CUDABlockProcessor(domain, block_size=8)
    >>> for block in processor.iterate_blocks_cuda():
    >>>     result = process_block_cuda(block)
"""

import numpy as np
from typing import Iterator, Tuple, Dict, Any, Optional, List, TYPE_CHECKING
import logging
from dataclasses import dataclass

try:
    import cupy as cp
    import cupyx.scipy.ndimage as cp_ndimage

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None
    cp_ndimage = None

if TYPE_CHECKING:
    if CUDA_AVAILABLE and cp is not None:
        CpArray = cp.ndarray
    else:
        CpArray = Any
else:
    CpArray = Any

from .domain import Domain
from .block_processor import BlockProcessor, BlockInfo
from .cuda_block_ops import (
    process_block_fft_cuda,
    process_block_convolution_cuda,
    process_block_gradient_cuda,
    process_block_bvp_cuda,
)
from .cuda_block_merge import (
    merge_blocks_cuda as _merge_blocks_cuda,
    create_weight_mask_cuda as _create_weight_mask_cuda,
)
from .cuda_block_utils import (
    extract_block_data_cuda as _extract_block_data_cuda,
    get_cuda_device_info as _get_cuda_device_info,
    cleanup_memory as _cleanup_memory,
)


class CUDABlockProcessor(BlockProcessor):
    """
    CUDA-optimized block processor for 7D domain operations.

    Physical Meaning:
        Provides CUDA-accelerated block processing for 7D phase field
        computations, enabling memory-efficient operations on large
        7D space-time domains using GPU acceleration.

    Mathematical Foundation:
        Implements CUDA-accelerated block decomposition of 7D space-time
        domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with GPU memory management.
    """

    def __init__(self, domain: Domain, block_size: int = 8, overlap: int = 2):
        """
        Initialize CUDA block processor.

        Physical Meaning:
            Sets up CUDA-accelerated block processing system for 7D phase field
            computations with GPU memory management and optimization.

        Args:
            domain (Domain): 7D computational domain.
            block_size (int): Size of each processing block.
            overlap (int): Overlap between adjacent blocks for continuity.
        """
        super().__init__(domain, block_size, overlap)

        # Check CUDA availability
        self.cuda_available = CUDA_AVAILABLE
        if not self.cuda_available:
            self.logger.warning("CUDA not available, falling back to CPU processing")
            return

        # Initialize CUDA
        self._initialize_cuda()

        self.logger.info(f"CUDA block processor initialized: {self.cuda_available}")

    def _initialize_cuda(self) -> None:
        """Initialize CUDA environment."""
        if not self.cuda_available:
            return

        try:
            # Get CUDA device info
            self.device = cp.cuda.Device()
            self.device_id = self.device.id

            # Get GPU memory info
            mempool = cp.get_default_memory_pool()
            self.total_memory = self.device.mem_info[1]  # Total memory
            self.free_memory = self.device.mem_info[0]  # Free memory

            # Set memory pool for efficient memory management
            mempool.set_limit(size=self.free_memory * 0.8)  # Use 80% of free memory

            self.logger.info(
                f"CUDA device {self.device_id}: {self.free_memory / 1e9:.1f} GB free memory"
            )

        except Exception as e:
            self.logger.error(f"CUDA initialization failed: {e}")
            self.cuda_available = False

    def iterate_blocks_cuda(self) -> Iterator[Tuple[CpArray, BlockInfo]]:
        """
        Iterate over all blocks in the 7D domain using CUDA.

        Physical Meaning:
            Yields blocks of the 7D domain for CUDA-accelerated processing,
            ensuring GPU memory efficiency and proper overlap handling.

        Yields:
            Tuple[CpArray, BlockInfo]: CUDA block data and block information.
        """
        if not self.cuda_available:
            # Fallback to CPU processing
            for block_data, block_info in super().iterate_blocks():
                yield block_data, block_info
            return

        block_id = 0

        # Iterate over all block combinations
        for block_indices in self._generate_block_indices():
            # Compute block boundaries
            start_indices, end_indices = self._compute_block_boundaries(block_indices)

            # Create block info
            block_info = BlockInfo(
                block_id=block_id,
                start_indices=start_indices,
                end_indices=end_indices,
                shape=tuple(
                    end - start for start, end in zip(start_indices, end_indices)
                ),
                global_offset=start_indices,
                memory_usage=self.block_memory_usage,
            )

            # Extract block data to GPU
            block_data = self._extract_block_data_cuda(start_indices, end_indices)

            if block_id % 10 == 0 or block_id == self.total_blocks - 1:
                self.logger.info(
                    f"[BlockProcessorCUDA] block {block_id+1}/{self.total_blocks} "
                    f"start={start_indices} end={end_indices}"
                )

            yield block_data, block_info
            block_id += 1

    def _extract_block_data_cuda(
        self, start_indices: Tuple[int, ...], end_indices: Tuple[int, ...]
    ) -> CpArray:
        """Extract block data to GPU memory (delegated to helper)."""
        return _extract_block_data_cuda(start_indices, end_indices)

    def process_block_cuda(
        self, block_data: CpArray, block_info: BlockInfo, operation: str = "fft"
    ) -> CpArray:
        """
        Process a single block with CUDA acceleration.

        Physical Meaning:
            Processes a single block of 7D phase field data with
            CUDA-accelerated operations for maximum performance.

        Args:
            block_data (CpArray): CUDA block data to process.
            block_info (BlockInfo): Block information.
            operation (str): Operation to perform on block.

        Returns:
            CpArray: CUDA-processed block data.
        """
        if not self.cuda_available:
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for block processing. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )

        if operation == "fft":
            return self._process_block_fft_cuda(block_data, block_info)
        elif operation == "convolution":
            return self._process_block_convolution_cuda(block_data, block_info)
        elif operation == "gradient":
            return self._process_block_gradient_cuda(block_data, block_info)
        elif operation == "bvp_solve":
            return self._process_block_bvp_cuda(block_data, block_info)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _process_block_fft_cuda(
        self, block_data: CpArray, block_info: BlockInfo
    ) -> CpArray:
        """Process block with CUDA FFT operation (delegated)."""
        return process_block_fft_cuda(block_data, block_info)

    def _process_block_convolution_cuda(
        self, block_data: CpArray, block_info: BlockInfo
    ) -> CpArray:
        """Process block with CUDA convolution operation (delegated)."""
        return process_block_convolution_cuda(block_data, block_info)

    def _process_block_gradient_cuda(
        self, block_data: CpArray, block_info: BlockInfo
    ) -> CpArray:
        """Process block with CUDA gradient operation (delegated)."""
        return process_block_gradient_cuda(block_data, block_info)

    def _process_block_bvp_cuda(
        self, block_data: CpArray, block_info: BlockInfo
    ) -> CpArray:
        """Process block with CUDA BVP solving (delegated)."""
        return process_block_bvp_cuda(block_data, block_info)

    def merge_blocks_cuda(
        self, processed_blocks: List[Tuple[CpArray, BlockInfo]]
    ) -> CpArray:
        """Merge processed blocks back into full domain using CUDA (delegated)."""
        if not self.cuda_available:
            cpu_blocks = [
                (cp.asnumpy(block_data), block_info)
                for block_data, block_info in processed_blocks
            ]
            cpu_result = super().merge_blocks(cpu_blocks)
            return cp.asarray(cpu_result)
        return _merge_blocks_cuda(
            processed_blocks, self.domain_shape, self.n_dims, self.overlap
        )

    def _create_weight_mask_cuda(self, block_info: BlockInfo) -> CpArray:
        """Create weight mask for overlap handling on GPU (delegated)."""
        return _create_weight_mask_cuda(
            block_info.shape,
            self.n_dims,
            self.overlap,
            block_info.start_indices,
            block_info.end_indices,
            self.domain_shape,
        )

    def optimize_block_size_cuda(self, available_memory_gb: float = None) -> int:
        """
        Optimize block size based on available GPU memory.

        Physical Meaning:
            Optimizes block size to fit within available GPU memory
            while maintaining processing efficiency.

        Args:
            available_memory_gb (float): Available GPU memory in GB.

        Returns:
            int: Optimized block size for CUDA processing.
        """
        if not self.cuda_available:
            return super().optimize_block_size(available_memory_gb or 8.0)

        if available_memory_gb is None:
            available_memory_gb = self.free_memory / 1e9

        effective_memory = available_memory_gb * 0.8
        max_block_size = int((effective_memory / (8 * 1e-9)) ** (1.0 / self.n_dims))
        optimized_size = max(4, min(max_block_size, self.block_size))
        self.logger.info(
            f"CUDA optimized block size: {optimized_size} (available GPU memory: {available_memory_gb:.1f} GB)"
        )
        return optimized_size

    def get_cuda_info(self) -> Dict[str, Any]:
        """Get CUDA device information."""
        if not self.cuda_available:
            return {"cuda_available": False}
        info = _get_cuda_device_info()
        info["cuda_available"] = True
        return info

    def get_memory_usage_cuda(self) -> Dict[str, Any]:
        """Get CUDA memory usage information."""
        base_usage = super().get_memory_usage()
        cuda_info = self.get_cuda_info()

        return {
            **base_usage,
            **cuda_info,
            "gpu_processing": self.cuda_available,
            "memory_pool_optimized": self.cuda_available,
        }

    def cleanup_cuda_memory(self) -> None:
        """Clean up CUDA memory."""
        if not self.cuda_available:
            return
        try:
            _cleanup_memory()
            self.logger.info("CUDA memory cleaned up")
        except Exception as e:
            self.logger.warning(f"CUDA memory cleanup failed: {e}")

    def __del__(self):
        """Cleanup CUDA memory on destruction."""
        if hasattr(self, "cuda_available") and self.cuda_available:
            self.cleanup_cuda_memory()
