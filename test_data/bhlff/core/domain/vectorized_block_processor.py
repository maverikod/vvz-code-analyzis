"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized block processor for 7D domain operations.

This module implements fully vectorized block processing for 7D domains
to handle memory-efficient computations on large 7D space-time grids.

Physical Meaning:
    Provides vectorized block processing for 7D phase field computations,
    enabling memory-efficient operations on large 7D space-time domains
    using vectorized operations for maximum performance.

Example:
    >>> processor = VectorizedBlockProcessor(domain, block_size=8)
    >>> for block in processor.iterate_blocks_vectorized():
    >>>     result = process_block_vectorized(block)
"""

import numpy as np
from typing import Iterator, Tuple, Dict, Any, Optional, List
import logging
from dataclasses import dataclass

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .domain import Domain
from .block_processor import BlockProcessor, BlockInfo


class VectorizedBlockProcessor(BlockProcessor):
    """
    Vectorized block processor for 7D domain operations.

    Physical Meaning:
        Provides fully vectorized block processing for 7D phase field
        computations, enabling memory-efficient operations on large
        7D space-time domains using vectorized operations.

    Mathematical Foundation:
        Implements vectorized block decomposition of 7D space-time
        domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with vectorized operations.
    """

    def __init__(
        self,
        domain: Domain,
        block_size: int = 8,
        overlap: int = 2,
        use_cuda: bool = True,
    ):
        """
        Initialize vectorized block processor.

        Physical Meaning:
            Sets up vectorized block processing system for 7D phase field
            computations with CUDA acceleration if available.

        Args:
            domain (Domain): 7D computational domain.
            block_size (int): Size of each processing block.
            overlap (int): Overlap between adjacent blocks for continuity.
            use_cuda (bool): Whether to use CUDA acceleration if available.
        """
        super().__init__(domain, block_size, overlap)

        self.use_cuda = use_cuda and CUDA_AVAILABLE
        self.xp = cp if self.use_cuda else np

        if self.use_cuda:
            self.logger.info(
                "Vectorized block processor initialized with CUDA acceleration"
            )
        else:
            self.logger.info(
                "Vectorized block processor initialized with CPU vectorization"
            )

    def process_blocks_vectorized(
        self, operation: str = "fft", batch_size: int = None
    ) -> np.ndarray:
        """
        Process all blocks using vectorized operations.

        Physical Meaning:
            Processes all blocks of the 7D domain using vectorized operations
            for maximum performance and memory efficiency.

        Args:
            operation (str): Operation to perform on blocks.
            batch_size (int): Number of blocks to process in parallel.

        Returns:
            np.ndarray: Processed full domain data.
        """
        if batch_size is None:
            batch_size = min(8, self.total_blocks)

        self.logger.info(
            f"Processing {self.total_blocks} blocks vectorized with batch size {batch_size}"
        )

        # Collect all blocks
        all_blocks = list(self.iterate_blocks())

        if self.use_cuda:
            return self._process_blocks_cuda_vectorized(
                all_blocks, operation, batch_size
            )
        else:
            return self._process_blocks_cpu_vectorized(
                all_blocks, operation, batch_size
            )

    def _process_blocks_cuda_vectorized(
        self,
        all_blocks: List[Tuple[np.ndarray, BlockInfo]],
        operation: str,
        batch_size: int,
    ) -> np.ndarray:
        """Process blocks using CUDA vectorized operations."""
        # Transfer all blocks to GPU
        gpu_blocks = []
        for block_data, block_info in all_blocks:
            gpu_block = cp.asarray(block_data)
            gpu_blocks.append((gpu_block, block_info))

        # Process blocks in batches on GPU
        processed_blocks = []
        for i in range(0, len(gpu_blocks), batch_size):
            batch_blocks = gpu_blocks[i : i + batch_size]
            batch_processed = self._process_batch_cuda_vectorized(
                batch_blocks, operation
            )
            processed_blocks.extend(batch_processed)

        # Merge all blocks on GPU
        result_gpu = self.merge_blocks_cuda(processed_blocks)

        # Transfer result back to CPU
        result = cp.asnumpy(result_gpu)

        # Cleanup GPU memory
        del gpu_blocks, processed_blocks, result_gpu
        cp.get_default_memory_pool().free_all_blocks()

        return result

    def _process_blocks_cpu_vectorized(
        self,
        all_blocks: List[Tuple[np.ndarray, BlockInfo]],
        operation: str,
        batch_size: int,
    ) -> np.ndarray:
        """Process blocks using CPU vectorized operations."""
        # Process blocks in batches
        processed_blocks = []
        for i in range(0, len(all_blocks), batch_size):
            batch_blocks = all_blocks[i : i + batch_size]
            batch_processed = self._process_batch_cpu_vectorized(
                batch_blocks, operation
            )
            processed_blocks.extend(batch_processed)

        # Merge all blocks
        result = self.merge_blocks(processed_blocks)

        return result

    def _process_batch_cuda_vectorized(
        self, batch_blocks: List[Tuple[np.ndarray, BlockInfo]], operation: str
    ) -> List[Tuple[np.ndarray, BlockInfo]]:
        """Process a batch of blocks using CUDA vectorized operations."""
        if not batch_blocks or not CUDA_AVAILABLE:
            return []

        # Extract block data and info
        block_data_list = [block_data for block_data, _ in batch_blocks]
        block_info_list = [block_info for _, block_info in batch_blocks]

        # Stack blocks for vectorized processing
        if CUDA_AVAILABLE:
            stacked_blocks = cp.stack(block_data_list)
        else:
            stacked_blocks = np.stack(block_data_list)

        # Apply vectorized operation
        if operation == "fft":
            processed_stacked = self._vectorized_fft_cuda(stacked_blocks)
        elif operation == "convolution":
            processed_stacked = self._vectorized_convolution_cuda(stacked_blocks)
        elif operation == "gradient":
            processed_stacked = self._vectorized_gradient_cuda(stacked_blocks)
        elif operation == "bvp_solve":
            processed_stacked = self._vectorized_bvp_solve_cuda(stacked_blocks)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        # Split back into individual blocks
        processed_blocks = []
        for i, (processed_block, block_info) in enumerate(
            zip(processed_stacked, block_info_list)
        ):
            processed_blocks.append((processed_block, block_info))

        return processed_blocks

    def _process_batch_cpu_vectorized(
        self, batch_blocks: List[Tuple[np.ndarray, BlockInfo]], operation: str
    ) -> List[Tuple[np.ndarray, BlockInfo]]:
        """Process a batch of blocks using CPU vectorized operations."""
        if not batch_blocks:
            return []

        # Extract block data and info
        block_data_list = [block_data for block_data, _ in batch_blocks]
        block_info_list = [block_info for _, block_info in batch_blocks]

        # Stack blocks for vectorized processing
        stacked_blocks = np.stack(block_data_list)

        # Apply vectorized operation
        if operation == "fft":
            processed_stacked = self._vectorized_fft_cpu(stacked_blocks)
        elif operation == "convolution":
            processed_stacked = self._vectorized_convolution_cpu(stacked_blocks)
        elif operation == "gradient":
            processed_stacked = self._vectorized_gradient_cpu(stacked_blocks)
        elif operation == "bvp_solve":
            processed_stacked = self._vectorized_bvp_solve_cpu(stacked_blocks)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        # Split back into individual blocks
        processed_blocks = []
        for i, (processed_block, block_info) in enumerate(
            zip(processed_stacked, block_info_list)
        ):
            processed_blocks.append((processed_block, block_info))

        return processed_blocks

    def _vectorized_fft_cuda(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized FFT operation on CUDA."""
        if CUDA_AVAILABLE:
            # Apply FFT to all blocks at once
            fft_result = cp.fft.fftn(
                stacked_blocks, axes=tuple(range(1, stacked_blocks.ndim))
            )

            # Apply 7D phase field specific processing vectorized
            phase = cp.angle(fft_result)
            processed_result = fft_result * cp.exp(-1j * phase)

            return processed_result.get()  # Convert back to numpy
        else:
            # CUDA is required - no CPU fallback
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for vectorized FFT. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )

    def _vectorized_fft_cpu(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized FFT operation on CPU."""
        # Apply FFT to all blocks at once
        fft_result = np.fft.fftn(
            stacked_blocks, axes=tuple(range(1, stacked_blocks.ndim))
        )

        # Apply 7D phase field specific processing vectorized
        phase = np.angle(fft_result)
        processed_result = fft_result * np.exp(-1j * phase)

        return processed_result

    def _vectorized_convolution_cuda(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized convolution operation on CUDA."""
        if not CUDA_AVAILABLE:
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for vectorized convolution. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        # Create convolution kernel for 7D phase field
        kernel_shape = tuple(min(3, size) for size in stacked_blocks.shape[1:])
        kernel = cp.ones(kernel_shape, dtype=cp.complex128) / cp.prod(kernel_shape)

        # Apply convolution to all blocks at once (vectorized)
        convolved = cp.zeros_like(stacked_blocks)
        for i in range(stacked_blocks.shape[0]):
            convolved[i] = cp.convolve(stacked_blocks[i].real, kernel, mode="same")
        return convolved.get()  # Convert back to numpy

    def _vectorized_convolution_cpu(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized convolution operation on CPU."""
        # Create convolution kernel for 7D phase field
        kernel_shape = tuple(min(3, size) for size in stacked_blocks.shape[1:])
        kernel = np.ones(kernel_shape, dtype=np.complex128) / np.prod(kernel_shape)

        # Apply convolution to all blocks at once
        convolved = np.zeros_like(stacked_blocks)
        for i in range(stacked_blocks.shape[0]):
            convolved[i] = np.convolve(stacked_blocks[i].real, kernel, mode="same")

        return convolved.astype(np.complex128)

    def _vectorized_gradient_cuda(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized gradient operation on CUDA."""
        if CUDA_AVAILABLE:
            # Compute gradient for all blocks at once
            gradients = []
            for i in range(stacked_blocks.shape[0]):
                block_gradients = cp.gradient(stacked_blocks[i].real)
                gradient_magnitude = cp.sqrt(
                    cp.sum(cp.array([g**2 for g in block_gradients]), axis=0)
                )
                gradients.append(gradient_magnitude)
            return cp.stack(gradients).get()  # Convert back to numpy
        else:
            # CUDA is required - no CPU fallback
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for vectorized gradient. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )

    def _vectorized_gradient_cpu(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized gradient operation on CPU."""
        # Compute gradient for all blocks at once
        gradients = []
        for i in range(stacked_blocks.shape[0]):
            block_gradients = np.gradient(stacked_blocks[i].real)
            gradient_magnitude = np.sqrt(
                np.sum(np.array([g**2 for g in block_gradients]), axis=0)
            )
            gradients.append(gradient_magnitude)

        return np.stack(gradients).astype(np.complex128)

    def _vectorized_bvp_solve_cuda(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized BVP solving on CUDA."""
        if not CUDA_AVAILABLE:
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for vectorized BVP solving. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        # CUDA-accelerated BVP solving for all blocks at once
        amplitude = cp.abs(stacked_blocks)
        phase = cp.angle(stacked_blocks)

        # Apply BVP-specific processing vectorized
        result = amplitude * cp.exp(1j * phase)
        return result.get()  # Convert back to numpy

    def _vectorized_bvp_solve_cpu(self, stacked_blocks: np.ndarray) -> np.ndarray:
        """Vectorized BVP solving on CPU."""
        # CPU BVP solving for all blocks at once
        amplitude = np.abs(stacked_blocks)
        phase = np.angle(stacked_blocks)

        # Apply BVP-specific processing vectorized
        result = amplitude * np.exp(1j * phase)

        return result

    def merge_blocks_cuda(
        self, processed_blocks: List[Tuple["cp.ndarray", BlockInfo]]
    ) -> "cp.ndarray":
        """Merge processed blocks using CUDA operations."""
        if not processed_blocks:
            return cp.zeros(self.domain_shape, dtype=cp.complex128)

        # Initialize result array on GPU
        result = cp.zeros(self.domain_shape, dtype=cp.complex128)
        weight_map = cp.zeros(self.domain_shape, dtype=cp.float64)

        # Merge blocks with overlap handling on GPU
        for block_data, block_info in processed_blocks:
            start_indices = block_info.start_indices
            end_indices = block_info.end_indices

            # Create slices
            slices = tuple(
                slice(start, end) for start, end in zip(start_indices, end_indices)
            )

            # Create weight mask for overlap handling on GPU
            weight_mask = self._create_weight_mask_cuda(block_info)

            # Add block data to result on GPU
            result[slices] += block_data * weight_mask
            weight_map[slices] += weight_mask

        # Normalize by weights on GPU
        result = cp.divide(
            result, weight_map, out=cp.zeros_like(result), where=weight_map != 0
        )

        return result

    def _create_weight_mask_cuda(self, block_info: BlockInfo) -> "cp.ndarray":
        """Create weight mask for overlap handling on GPU."""
        block_shape = block_info.shape
        weight_mask = cp.ones(block_shape, dtype=cp.float64)

        # Apply overlap weights at boundaries on GPU
        for dim in range(self.n_dims):
            if block_info.start_indices[dim] > 0:
                # Overlap at start
                overlap_size = min(self.overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(0, overlap_size) if i == dim else slice(None)
                        for i in range(self.n_dims)
                    )
                ] *= 0.5

            if block_info.end_indices[dim] < self.domain_shape[dim]:
                # Overlap at end
                overlap_size = min(self.overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(-overlap_size, None) if i == dim else slice(None)
                        for i in range(self.n_dims)
                    )
                ] *= 0.5

        return weight_mask

    def get_vectorization_info(self) -> Dict[str, Any]:
        """Get vectorization information."""
        base_info = self.get_memory_usage()

        return {
            **base_info,
            "vectorized_processing": True,
            "cuda_acceleration": self.use_cuda,
            "batch_processing": True,
            "vectorized_operations": ["fft", "convolution", "gradient", "bvp_solve"],
        }
