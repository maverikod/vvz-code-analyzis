"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA streams for parallel block processing.

This module provides CUDA streams for parallel processing of multiple blocks
simultaneously, enabling better GPU utilization and performance.

Physical Meaning:
    Uses CUDA streams to process multiple blocks in parallel on GPU,
    enabling better GPU utilization and performance for 7D phase field
    computations in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Processes multiple blocks simultaneously using CUDA streams:
    - Multiple streams process different blocks in parallel
    - Overlaps computation and memory transfers
    - Maximizes GPU utilization for 7D operations

Example:
    >>> from bhlff.core.domain.cuda_stream_block_processor import CUDAStreamBlockProcessor
    >>> processor = CUDAStreamBlockProcessor(domain, num_streams=4)
    >>> result = processor.process_blocks_streamed(blocks, operation="bvp_solve")
"""

import logging
from typing import List, Tuple, Optional, Callable, Any
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .block_processor import BlockInfo

logger = logging.getLogger(__name__)


class CUDAStreamBlockProcessor:
    """
    CUDA streams for parallel block processing.
    
    Physical Meaning:
        Uses CUDA streams to process multiple blocks in parallel on GPU,
        enabling better GPU utilization and performance for 7D phase field
        computations.
        
    Mathematical Foundation:
        Processes multiple blocks simultaneously using CUDA streams:
        - Multiple streams process different blocks in parallel
        - Overlaps computation and memory transfers
        - Maximizes GPU utilization for 7D operations
        
    Attributes:
        domain_shape (Tuple[int, ...]): Shape of 7D domain.
        num_streams (int): Number of CUDA streams to use.
        streams (List[cp.cuda.Stream]): List of CUDA streams.
        dtype (np.dtype): Data type for computations.
    """
    
    def __init__(
        self,
        domain_shape: Tuple[int, ...],
        num_streams: int = 4,
        dtype: np.dtype = np.complex128,
    ):
        """
        Initialize CUDA stream block processor.
        
        Physical Meaning:
            Sets up CUDA streams for parallel block processing on GPU.
            
        Args:
            domain_shape (Tuple[int, ...]): Shape of 7D domain.
            num_streams (int): Number of CUDA streams to use (default: 4).
            dtype (np.dtype): Data type for computations (default: complex128).
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA not available. CUDAStreamBlockProcessor requires CUDA."
            )
        
        self.domain_shape = domain_shape
        self.num_streams = num_streams
        self.dtype = dtype
        
        # Create CUDA streams
        self.streams = [cp.cuda.Stream() for _ in range(num_streams)]
        
        logger.info(
            f"CUDAStreamBlockProcessor initialized with {num_streams} streams "
            f"for domain {domain_shape}"
        )
    
    def process_blocks_streamed(
        self,
        blocks: List[Tuple[np.ndarray, BlockInfo]],
        operation: str,
        operation_func: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ) -> List[np.ndarray]:
        """
        Process blocks using CUDA streams for parallel execution.
        
        Physical Meaning:
            Processes multiple blocks in parallel using CUDA streams,
            enabling better GPU utilization and performance.
            
        Args:
            blocks (List[Tuple[np.ndarray, BlockInfo]]): List of blocks to process.
            operation (str): Operation name (for logging).
            operation_func (Optional[Callable]): Operation function to apply.
                If None, uses default operation based on operation name.
                
        Returns:
            List[np.ndarray]: List of processed blocks.
        """
        if not blocks:
            return []
        
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available for stream processing")
        
        # Distribute blocks across streams
        blocks_per_stream = (len(blocks) + self.num_streams - 1) // self.num_streams
        
        # Process blocks in parallel using streams
        results = [None] * len(blocks)
        
        for stream_idx in range(self.num_streams):
            stream = self.streams[stream_idx]
            start_idx = stream_idx * blocks_per_stream
            end_idx = min(start_idx + blocks_per_stream, len(blocks))
            
            if start_idx >= len(blocks):
                break
            
            stream_blocks = blocks[start_idx:end_idx]
            
            # Process blocks in this stream
            with stream:
                stream_results = self._process_stream_blocks(
                    stream_blocks, operation, operation_func, stream
                )
                
                # Store results
                for i, result in enumerate(stream_results):
                    results[start_idx + i] = result
        
        # Synchronize all streams
        for stream in self.streams:
            stream.synchronize()
        
        logger.info(
            f"Processed {len(blocks)} blocks using {self.num_streams} CUDA streams"
        )
        
        return results
    
    def _process_stream_blocks(
        self,
        stream_blocks: List[Tuple[np.ndarray, BlockInfo]],
        operation: str,
        operation_func: Optional[Callable[[np.ndarray], np.ndarray]],
        stream: "cp.cuda.Stream",
    ) -> List[np.ndarray]:
        """
        Process blocks in a single stream.
        
        Physical Meaning:
            Processes blocks in a single CUDA stream, transferring data
            and computing in parallel with other streams.
            
        Args:
            stream_blocks (List[Tuple[np.ndarray, BlockInfo]]): Blocks for this stream.
            operation (str): Operation name.
            operation_func (Optional[Callable]): Operation function.
            stream (cp.cuda.Stream): CUDA stream to use.
            
        Returns:
            List[np.ndarray]: Processed blocks.
        """
        results = []
        
        for block_data, block_info in stream_blocks:
            # Transfer block to GPU asynchronously
            block_gpu = cp.asarray(block_data, dtype=self.dtype)
            
            # Apply operation
            if operation_func is not None:
                result_gpu = operation_func(block_gpu)
            else:
                result_gpu = self._apply_default_operation(block_gpu, operation)
            
            # Transfer result back to CPU asynchronously
            result = cp.asnumpy(result_gpu)
            results.append(result)
            
            # Clean up GPU memory
            del block_gpu, result_gpu
        
        return results
    
    def _apply_default_operation(
        self, block_gpu: "cp.ndarray", operation: str
    ) -> "cp.ndarray":
        """
        Apply default operation to block.
        
        Physical Meaning:
            Applies default operation based on operation name.
            
        Args:
            block_gpu (cp.ndarray): Block on GPU.
            operation (str): Operation name.
            
        Returns:
            cp.ndarray: Processed block on GPU.
        """
        if operation == "fft":
            return cp.fft.fftn(block_gpu, norm="ortho")
        elif operation == "ifft":
            return cp.fft.ifftn(block_gpu, norm="ortho")
        elif operation == "abs":
            return cp.abs(block_gpu)
        elif operation == "angle":
            return cp.angle(block_gpu)
        elif operation == "real":
            return cp.real(block_gpu)
        elif operation == "imag":
            return cp.imag(block_gpu)
        else:
            logger.warning(f"Unknown operation: {operation}, returning block as-is")
            return block_gpu
    
    def cleanup(self) -> None:
        """
        Clean up CUDA streams and GPU memory.
        
        Physical Meaning:
            Cleans up CUDA streams and frees GPU memory.
        """
        # Synchronize all streams
        for stream in self.streams:
            stream.synchronize()
        
        # Free GPU memory
        if CUDA_AVAILABLE:
            cp.get_default_memory_pool().free_all_blocks()
        
        logger.debug("CUDA streams cleaned up")

