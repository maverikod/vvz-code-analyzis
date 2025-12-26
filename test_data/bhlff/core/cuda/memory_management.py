"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA memory management utilities with pinned memory and async operations.

This module provides memory management utilities for efficient CPU-GPU
transfers using pinned memory and asynchronous operations with CUDA streams.

Physical Meaning:
    Provides memory management utilities for efficient data transfers
    between CPU and GPU using pinned (page-locked) memory and asynchronous
    operations with CUDA streams for overlapping computation and transfers.

Mathematical Foundation:
    Implements memory management patterns for optimal GPU utilization:
    - Pinned memory for fast CPU-GPU transfers
    - Asynchronous operations with CUDA streams
    - Overlapping computation and memory transfers

Example:
    >>> manager = CUDAMemoryManager()
    >>> field_pinned = manager.allocate_pinned(field_shape, np.complex128)
    >>> result = manager.async_transfer_and_compute(field_pinned, operation)
"""

import numpy as np
import logging
from typing import Tuple, Callable, Optional, Any
from contextlib import contextmanager

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class CUDAMemoryManager:
    """
    CUDA memory manager with pinned memory and async operations.
    
    Physical Meaning:
        Manages CUDA memory operations with pinned memory allocation
        and asynchronous transfers using CUDA streams for optimal
        GPU utilization and performance.
        
    Mathematical Foundation:
        Provides memory management for efficient GPU computations:
        - Pinned memory for fast CPU-GPU transfers
        - Asynchronous operations with CUDA streams
        - Overlapping computation and memory transfers
        
    Attributes:
        _default_stream (cp.cuda.Stream): Default CUDA stream.
        _pinned_pool: CuPy pinned memory pool.
    """
    
    def __init__(self):
        """
        Initialize CUDA memory manager.
        
        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for CUDAMemoryManager. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        self._default_stream = cp.cuda.Stream.null
        self._pinned_pool = cp.get_default_pinned_memory_pool()
        
        logger.info("CUDAMemoryManager initialized")
    
    def allocate_pinned(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
    ) -> np.ndarray:
        """
        Allocate pinned (page-locked) memory for efficient CPU-GPU transfers.
        
        Physical Meaning:
            Allocates pinned memory on CPU that can be efficiently transferred
            to/from GPU, enabling faster data transfers and overlapping
            computation with transfers.
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            np.ndarray: Pinned memory array on CPU.
        """
        try:
            # Calculate required memory
            required = int(np.prod(shape) * np.dtype(dtype).itemsize)
            
            # Allocate pinned memory using CuPy pinned memory pool
            pinned_mem = cp.cuda.alloc_pinned_memory(required)
            
            # Create numpy array from pinned memory buffer
            array = np.ndarray(
                shape=shape,
                dtype=dtype,
                buffer=pinned_mem,
            )
            
            logger.debug(
                f"Allocated {required / (1024**3):.2f} GB pinned memory "
                f"(shape: {shape}, dtype: {dtype})"
            )
            
            return array
        except Exception as e:
            logger.error(f"Failed to allocate pinned memory: {e}")
            raise RuntimeError(f"Failed to allocate pinned memory: {e}") from e
    
    def async_transfer_and_compute(
        self,
        field_cpu: np.ndarray,
        operation: Callable[["cp.ndarray"], "cp.ndarray"],
        stream: Optional["cp.cuda.Stream"] = None,
    ) -> "cp.ndarray":
        """
        Asynchronous transfer and computation with overlapping.
        
        Physical Meaning:
            Performs asynchronous transfer of data from CPU to GPU and
            computation on GPU using CUDA streams, enabling overlapping
            of computation and memory transfers for optimal performance.
            
        Mathematical Foundation:
            Uses CUDA streams to overlap:
            - CPU-GPU memory transfer
            - GPU computation
            - GPU-CPU memory transfer (if needed)
            
        Args:
            field_cpu (np.ndarray): Input field on CPU (preferably pinned memory).
            operation (Callable): GPU operation to perform on field.
            stream (Optional[cp.cuda.Stream]): CUDA stream to use (default: None).
            
        Returns:
            cp.ndarray: Result on GPU.
        """
        if stream is None:
            stream = self._default_stream
        
        with stream:
            # Asynchronous transfer to GPU
            field_gpu = cp.asarray(field_cpu)
            
            # Perform computation
            result = operation(field_gpu)
        
        # Synchronize stream to ensure completion
        stream.synchronize()
        
        return result
    
    def async_transfer_to_gpu(
        self,
        field_cpu: np.ndarray,
        stream: Optional["cp.cuda.Stream"] = None,
    ) -> "cp.ndarray":
        """
        Asynchronous transfer from CPU to GPU.
        
        Physical Meaning:
            Transfers data from CPU to GPU asynchronously using CUDA streams,
            enabling overlapping with other operations.
            
        Args:
            field_cpu (np.ndarray): Input field on CPU (preferably pinned memory).
            stream (Optional[cp.cuda.Stream]): CUDA stream to use (default: None).
            
        Returns:
            cp.ndarray: Field on GPU.
        """
        if stream is None:
            stream = self._default_stream
        
        with stream:
            field_gpu = cp.asarray(field_cpu)
        
        return field_gpu
    
    def async_transfer_to_cpu(
        self,
        field_gpu: "cp.ndarray",
        stream: Optional["cp.cuda.Stream"] = None,
    ) -> np.ndarray:
        """
        Asynchronous transfer from GPU to CPU.
        
        Physical Meaning:
            Transfers data from GPU to CPU asynchronously using CUDA streams,
            enabling overlapping with other operations.
            
        Args:
            field_gpu (cp.ndarray): Input field on GPU.
            stream (Optional[cp.cuda.Stream]): CUDA stream to use (default: None).
            
        Returns:
            np.ndarray: Field on CPU.
        """
        if stream is None:
            stream = self._default_stream
        
        with stream:
            field_cpu = cp.asnumpy(field_gpu)
        
        stream.synchronize()
        return field_cpu
    
    @contextmanager
    def async_context(self, stream: Optional["cp.cuda.Stream"] = None):
        """
        Context manager for asynchronous operations.
        
        Physical Meaning:
            Provides a context manager for asynchronous CUDA operations,
            automatically synchronizing the stream on exit.
            
        Args:
            stream (Optional[cp.cuda.Stream]): CUDA stream to use (default: None).
            
        Yields:
            cp.cuda.Stream: CUDA stream for operations.
        """
        if stream is None:
            stream = cp.cuda.Stream()
        
        try:
            with stream:
                yield stream
        finally:
            stream.synchronize()
    
    def create_stream(self) -> "cp.cuda.Stream":
        """
        Create a new CUDA stream for asynchronous operations.
        
        Physical Meaning:
            Creates a new CUDA stream for independent asynchronous operations,
            enabling parallel execution of multiple operations.
            
        Returns:
            cp.cuda.Stream: New CUDA stream.
        """
        return cp.cuda.Stream()
    
    def synchronize(self, stream: Optional["cp.cuda.Stream"] = None) -> None:
        """
        Synchronize CUDA stream.
        
        Physical Meaning:
            Synchronizes CUDA stream to ensure all operations complete
            before proceeding.
            
        Args:
            stream (Optional[cp.cuda.Stream]): CUDA stream to synchronize (default: None).
        """
        if stream is None:
            stream = self._default_stream
        
        stream.synchronize()


# Convenience functions
def allocate_pinned_memory(
    shape: Tuple[int, ...],
    dtype: np.dtype = np.complex128,
) -> np.ndarray:
    """
    Allocate pinned memory for efficient CPU-GPU transfers.
    
    Physical Meaning:
        Convenience function for allocating pinned memory for efficient
        CPU-GPU transfers.
        
    Args:
        shape (Tuple[int, ...]): Array shape.
        dtype (np.dtype): Data type (default: complex128).
        
    Returns:
        np.ndarray: Pinned memory array on CPU.
    """
    manager = CUDAMemoryManager()
    return manager.allocate_pinned(shape, dtype)


def async_transfer_and_compute(
    field_cpu: np.ndarray,
    operation: Callable[["cp.ndarray"], "cp.ndarray"],
    stream: Optional["cp.cuda.Stream"] = None,
) -> "cp.ndarray":
    """
    Asynchronous transfer and computation with overlapping.
    
    Physical Meaning:
        Convenience function for asynchronous transfer and computation
        with overlapping.
        
    Args:
        field_cpu (np.ndarray): Input field on CPU (preferably pinned memory).
        operation (Callable): GPU operation to perform on field.
        stream (Optional[cp.cuda.Stream]): CUDA stream to use (default: None).
        
    Returns:
        cp.ndarray: Result on GPU.
    """
    manager = CUDAMemoryManager()
    return manager.async_transfer_and_compute(field_cpu, operation, stream)

