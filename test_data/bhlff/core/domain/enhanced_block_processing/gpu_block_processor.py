"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU block processing for 7D fields with CUDA optimization.

This module implements GPU-accelerated block processing with 7D operations,
vectorization, and backpressure management for optimal GPU memory usage.
"""

import numpy as np
import logging
import gc
from typing import Union, Any, Dict

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .gpu_block_operations import GPUBlockOperations
from .gpu_block_utils import GPUBlockUtils


class GPUBlockProcessor:
    """
    GPU block processor with 7D operations and vectorization.

    Physical Meaning:
        Provides GPU-accelerated block processing for 7D phase fields
        using vectorized CUDA operations and 7D-specific operations
        (7D Laplacian) with optimal memory management.

    Mathematical Foundation:
        Implements block-based processing with 7D operations:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - Vectorized CUDA kernels for optimal performance
        - Backpressure for memory management
    """

    def __init__(self, cuda_available: bool, logger: logging.Logger = None):
        """
        Initialize GPU block processor.

        Args:
            cuda_available (bool): Whether CUDA is available.
            logger (logging.Logger): Logger instance.
        """
        self.cuda_available = cuda_available and CUDA_AVAILABLE
        self.logger = logger or logging.getLogger(__name__)

        # Initialize operations and utilities
        self.operations = GPUBlockOperations(self.cuda_available, self.logger)
        self.utils = GPUBlockUtils(self.cuda_available, self.logger)
        
        # Initialize batched FFT operations for efficient batch processing
        self._batched_fft = None
        if self.cuda_available:
            try:
                from ...fft.batched_fft_operations import BatchedFFTOperations
                # Will be initialized with domain shape when needed
                self._batched_fft_class = BatchedFFTOperations
            except ImportError:
                self.logger.warning("BatchedFFTOperations not available, using single-block FFT")
                self._batched_fft_class = None
        
        # Initialize CUDA stream processor for parallel block processing
        self._stream_processor = None
        if self.cuda_available:
            try:
                from ...domain.cuda_stream_block_processor import CUDAStreamBlockProcessor
                self._stream_processor_class = CUDAStreamBlockProcessor
            except ImportError:
                self.logger.warning("CUDAStreamBlockProcessor not available, using sequential processing")
                self._stream_processor_class = None

    def process_blocks(
        self,
        field: np.ndarray,
        operation: str,
        block_iterator,
        use_7d_operations: bool = True,
        **kwargs
    ) -> tuple:
        """
        Process 7D field in blocks on GPU with vectorization and backpressure.

        Physical Meaning:
            Processes 7D field in blocks on GPU using vectorized CUDA operations
            and 7D-specific operations (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²) for optimal
            performance. Uses backpressure to manage GPU memory efficiently with
            80% memory usage limit for 7D operations. Implements optimized batch
            processing with vectorized operations for maximum GPU utilization.

        Mathematical Foundation:
            Implements block-based processing with 7D Laplacian:
            - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
            - Vectorized CUDA kernels for all 7 dimensions
            - Backpressure with 80% GPU memory limit for 7D operations
            - Batch processing for optimal GPU occupancy

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            block_iterator: Iterator over blocks (block_data, block_info).
            use_7d_operations (bool): Use 7D-specific operations (default: True).
            **kwargs: Additional parameters including:
                - use_backpressure (bool): Enable backpressure management (default: True for 7D).

        Returns:
            tuple: (Processed field, block count).
        """
        use_7d_operations = kwargs.get("use_7d_operations", use_7d_operations)
        use_backpressure = kwargs.get("use_backpressure", use_7d_operations)
        
        self.logger.info(
            f"Processing with GPU blocks (7D operations: {use_7d_operations}, "
            f"backpressure: {use_backpressure})"
        )

        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for GPU block processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        # Transfer to GPU with vectorized transfer
        # Use pinned memory for faster CPU-GPU transfer
        field_gpu = cp.asarray(field)
        result_gpu = cp.zeros_like(field_gpu, dtype=cp.complex128)

        try:
            # Process in blocks on GPU with backpressure and vectorization
            block_count = 0
            # Optimized batch processing for better GPU utilization
            # For 7D operations, use smaller batches to respect 80% memory limit
            # For other operations, can use larger batches
            batch_size = 4 if use_7d_operations else 8  # Smaller batches for 7D operations
            
            # Pre-allocate block buffer for vectorized operations
            block_buffer = []
            block_infos = []
            
            for block_data, block_info in block_iterator:
                # Extract block on GPU with vectorized slicing
                block_gpu = self.utils.extract_block_gpu(field_gpu, block_info)
                block_buffer.append(block_gpu)
                block_infos.append(block_info)

                # Process in batches for better GPU utilization with vectorization
                if len(block_buffer) >= batch_size:
                    # Process batch with vectorized operations
                    processed_batch = self._process_block_batch_gpu_vectorized(
                        block_buffer, operation, use_7d_operations, **kwargs
                    )
                    # Merge batch results with vectorized merging
                    for block_info, processed_block in zip(block_infos, processed_batch):
                        self.utils.merge_block_result_gpu(result_gpu, processed_block, block_info)
                        block_count += 1
                    block_buffer.clear()
                    block_infos.clear()

                # Backpressure: periodically synchronize and check memory
                # For 7D operations with backpressure, use more frequent checks
                # For 7D operations, use 80% memory limit (project requirement)
                if use_backpressure:
                    # More frequent checks for 7D operations due to higher memory usage
                    check_interval = 5 if use_7d_operations else 10
                    if block_count % check_interval == 0:
                        cp.cuda.Stream.null.synchronize()
                        self.utils.check_gpu_memory_pressure(use_7d_operations=use_7d_operations)

            # Process remaining blocks in buffer
            if block_buffer:
                processed_batch = self._process_block_batch_gpu_vectorized(
                    block_buffer, operation, use_7d_operations, **kwargs
                )
                for block_info, processed_block in zip(block_infos, processed_batch):
                    self.utils.merge_block_result_gpu(result_gpu, processed_block, block_info)
                    block_count += 1

            # Synchronize before transfer
            cp.cuda.Stream.null.synchronize()

            # Transfer back to CPU
            result = cp.asnumpy(result_gpu)

        finally:
            # Cleanup GPU memory
            del field_gpu, result_gpu
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()

        return result, block_count


    def _process_block_batch_gpu(
        self,
        block_buffer: list,
        operation: str,
        use_7d_operations: bool,
        **kwargs
    ) -> list:
        """
        Process a batch of blocks on GPU with vectorized operations.

        Physical Meaning:
            Processes multiple 7D blocks in batch on GPU using vectorized CUDA
            operations for optimal GPU utilization. All blocks are processed
            using 7D operations (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²) when enabled.

        Mathematical Foundation:
            Uses vectorized CUDA kernels for batch processing:
            - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for all blocks
            - Vectorized operations across batch for optimal GPU occupancy

        Args:
            block_buffer (list): List of (block_gpu, block_info) tuples.
            operation (str): Operation to perform.
            use_7d_operations (bool): Use 7D-specific operations.
            **kwargs: Additional parameters.

        Returns:
            list: List of processed blocks on GPU.
        """
        processed_batch = []
        
        # Process each block with 7D operations if enabled
        # Always prefer 7D operations for 7D fields
        for block_gpu, _ in block_buffer:
            if use_7d_operations and self.operations._7d_ops is not None:
                processed_block = self.operations.process_single_block_gpu_7d(
                    block_gpu, operation, **kwargs
                )
            else:
                # Fallback to non-7D operations only if explicitly disabled
                if use_7d_operations:
                    self.logger.warning(
                        "7D operations requested but 7D ops backend not available. "
                        "Using fallback processing."
                    )
                processed_block = self.operations.process_single_block_gpu(
                    block_gpu, operation, **kwargs
                )
            processed_batch.append(processed_block)
        
        return processed_batch

    def _process_block_batch_gpu_vectorized(
        self,
        block_buffer: list,
        operation: str,
        use_7d_operations: bool,
        **kwargs
    ) -> list:
        """
        Process a batch of blocks on GPU with optimized vectorized operations.

        Physical Meaning:
            Processes multiple 7D blocks in batch on GPU using highly optimized
            vectorized CUDA operations for maximum GPU utilization. All blocks are
            processed using 7D operations (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²) when
            enabled. Uses batched FFT operations and CUDA streams for optimal
            GPU occupancy and parallel processing.

        Mathematical Foundation:
            Uses optimized vectorized CUDA kernels for batch processing:
            - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for all blocks
            - Batched FFT operations for multiple blocks simultaneously
            - CUDA streams for parallel processing of blocks
            - Vectorized operations across entire batch for optimal GPU occupancy

        Args:
            block_buffer (list): List of block_gpu arrays (without block_info).
            operation (str): Operation to perform.
            use_7d_operations (bool): Use 7D-specific operations.
            **kwargs: Additional parameters including:
                - use_batched_fft (bool): Use batched FFT for FFT operations (default: True).
                - use_streams (bool): Use CUDA streams for parallel processing (default: True).

        Returns:
            list: List of processed blocks on GPU.
        """
        if not block_buffer:
            return []
        
        # Validate all blocks are 7D
        for block_gpu in block_buffer:
            if block_gpu.ndim != 7:
                raise ValueError(
                    f"Expected 7D block for GPU processing, got {block_gpu.ndim}D. "
                    f"Shape: {block_gpu.shape}"
                )
        
        # Use batched FFT for FFT operations if available
        use_batched_fft = kwargs.get("use_batched_fft", True)
        if operation in ("fft", "ifft") and use_batched_fft and self._batched_fft_class is not None:
            return self._process_batch_with_batched_fft(block_buffer, operation, **kwargs)
        
        # Use CUDA streams for parallel processing if available
        use_streams = kwargs.get("use_streams", True)
        if use_streams and self._stream_processor_class is not None and len(block_buffer) > 1:
            return self._process_batch_with_streams(block_buffer, operation, use_7d_operations, **kwargs)
        
        # Fallback to sequential processing with 7D operations
        processed_batch = []
        for block_gpu in block_buffer:
            if use_7d_operations and self.operations._7d_ops is not None:
                # Use optimized 7D operations with vectorization
                processed_block = self.operations.process_single_block_gpu_7d(
                    block_gpu, operation, **kwargs
                )
            else:
                # Fallback to non-7D operations only if explicitly disabled
                if use_7d_operations:
                    self.logger.warning(
                        "7D operations requested but 7D ops backend not available. "
                        "Using fallback processing."
                    )
                processed_block = self.operations.process_single_block_gpu(
                    block_gpu, operation, **kwargs
                )
            processed_batch.append(processed_block)
        
        return processed_batch
    
    def _process_batch_with_batched_fft(
        self,
        block_buffer: list,
        operation: str,
        **kwargs
    ) -> list:
        """
        Process batch of blocks using batched FFT operations.
        
        Physical Meaning:
            Processes multiple blocks using batched FFT operations for optimal
            GPU utilization and performance.
            
        Args:
            block_buffer (list): List of block_gpu arrays.
            operation (str): Operation name ("fft" or "ifft").
            **kwargs: Additional parameters.
            
        Returns:
            list: List of processed blocks on GPU.
        """
        # Initialize batched FFT if not already done
        if self._batched_fft is None and block_buffer:
            block_shape = block_buffer[0].shape
            self._batched_fft = self._batched_fft_class(
                domain_shape=block_shape,
                dtype=block_buffer[0].dtype,
                gpu_memory_ratio=0.8,  # Use 80% GPU memory (project requirement)
            )
        
        # Convert GPU arrays to CPU for batched FFT (it handles GPU internally)
        block_cpu_list = [cp.asnumpy(block) for block in block_buffer]
        
        # Perform batched FFT
        if operation == "fft":
            processed_cpu_list = self._batched_fft.batched_fftn(
                block_cpu_list, normalization="ortho"
            )
        elif operation == "ifft":
            processed_cpu_list = self._batched_fft.batched_ifftn(
                block_cpu_list, normalization="ortho"
            )
        else:
            # Fallback to sequential processing
            return self._process_block_batch_gpu_vectorized(
                block_buffer, operation, True, use_batched_fft=False, **kwargs
            )
        
        # Convert back to GPU arrays
        processed_batch = [cp.asarray(block) for block in processed_cpu_list]
        
        return processed_batch
    
    def _process_batch_with_streams(
        self,
        block_buffer: list,
        operation: str,
        use_7d_operations: bool,
        **kwargs
    ) -> list:
        """
        Process batch of blocks using CUDA streams for parallel processing.
        
        Physical Meaning:
            Processes multiple blocks in parallel using CUDA streams for optimal
            GPU utilization and performance.
            
        Args:
            block_buffer (list): List of block_gpu arrays.
            operation (str): Operation to perform.
            use_7d_operations (bool): Use 7D-specific operations.
            **kwargs: Additional parameters.
            
        Returns:
            list: List of processed blocks on GPU.
        """
        # Initialize stream processor if not already done
        if self._stream_processor is None and block_buffer:
            block_shape = block_buffer[0].shape
            num_streams = min(4, len(block_buffer))  # Use up to 4 streams
            self._stream_processor = self._stream_processor_class(
                domain_shape=block_shape,
                num_streams=num_streams,
                dtype=block_buffer[0].dtype,
            )
        
        # Create block info list (dummy BlockInfo for stream processor)
        from ..block_processor import BlockInfo
        block_info_list = [
            BlockInfo(
                block_id=i,
                start_indices=tuple(0 for _ in range(7)),
                end_indices=block.shape,
                shape=block.shape,
                global_offset=tuple(0 for _ in range(7)),
                memory_usage=block.nbytes / (1024**2),
            )
            for i, block in enumerate(block_buffer)
        ]
        
        # Create operation function
        def operation_func(block_gpu):
            if use_7d_operations and self.operations._7d_ops is not None:
                return self.operations.process_single_block_gpu_7d(
                    block_gpu, operation, **kwargs
                )
            else:
                return self.operations.process_single_block_gpu(
                    block_gpu, operation, **kwargs
                )
        
        # Process blocks using streams
        blocks_with_info = list(zip(block_buffer, block_info_list))
        processed_cpu_list = self._stream_processor.process_blocks_streamed(
            blocks_with_info, operation, operation_func
        )
        
        # Convert back to GPU arrays
        processed_batch = [cp.asarray(block) for block in processed_cpu_list]
        
        return processed_batch


