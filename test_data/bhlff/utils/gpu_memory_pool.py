"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU memory pool management for BHLFF project.

This module provides GPU memory pool management with automatic
memory limit enforcement and efficient memory allocation.

Physical Meaning:
    Manages GPU memory pools for phase field computations, ensuring
    efficient memory utilization (80% by default) and preventing
    memory overflow with automatic limit enforcement.

Mathematical Foundation:
    Provides memory pool management with configurable memory limits
    for optimal GPU memory utilization in 7D phase field computations.

Example:
    >>> pool = GPUMemoryPool(max_memory_ratio=0.8)
    >>> array = pool.allocate((64, 64, 64, 16, 16, 16, 100), np.complex128)
"""

import logging
from typing import Tuple, Optional
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class GPUMemoryPool:
    """
    GPU memory pool with automatic memory limit enforcement.
    
    Physical Meaning:
        Manages GPU memory pools for phase field computations, ensuring
        efficient memory utilization (80% by default) and preventing
        memory overflow with automatic limit enforcement.
        
    Mathematical Foundation:
        Provides memory pool management with configurable memory limits
        for optimal GPU memory utilization in 7D phase field computations.
        
    Attributes:
        max_memory_ratio (float): Maximum fraction of GPU memory to use.
        pool: Default CuPy memory pool.
        pinned_pool: Default CuPy pinned memory pool.
        max_memory (int): Maximum memory in bytes.
        cuda_available (bool): Whether CUDA is available.
    """
    
    def __init__(self, max_memory_ratio: float = 0.8):
        """
        Initialize GPU memory pool.
        
        Physical Meaning:
            Sets up GPU memory pool with specified memory limit ratio
            for efficient memory management during computations.
            
        Args:
            max_memory_ratio (float): Maximum fraction of GPU memory to use
                (default: 0.8 for 80% usage).
        """
        self.max_memory_ratio = max_memory_ratio
        self.cuda_available = CUDA_AVAILABLE
        
        if not self.cuda_available:
            logger.warning(
                "CUDA not available - GPUMemoryPool will not function properly"
            )
            self.pool = None
            self.pinned_pool = None
            self.max_memory = 0
        else:
            self.pool = cp.get_default_memory_pool()
            self.pinned_pool = cp.get_default_pinned_memory_pool()
            self.max_memory = self._get_max_memory() * max_memory_ratio
            
            logger.info(
                f"GPU memory pool initialized: max_memory={self.max_memory / (1024**3):.2f} GB "
                f"({max_memory_ratio:.0%} of total GPU memory)"
            )
    
    def _get_max_memory(self) -> int:
        """
        Get maximum GPU memory.
        
        Physical Meaning:
            Retrieves total GPU memory available for computations.
            
        Returns:
            int: Total GPU memory in bytes.
        """
        if not self.cuda_available:
            return 0
        
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            return mem_info[1]  # Total memory
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
            return 0
    
    def allocate(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
    ) -> "cp.ndarray":
        """
        Allocate memory from pool with limit check.
        
        Physical Meaning:
            Allocates GPU memory for array with specified shape and dtype,
            ensuring the allocation does not exceed the memory limit.
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            cp.ndarray: Allocated GPU array.
            
        Raises:
            MemoryError: If required memory exceeds limit.
            RuntimeError: If CUDA is not available.
        """
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - cannot allocate GPU memory")
        
        # Calculate required memory
        required = int(np.prod(shape) * np.dtype(dtype).itemsize)
        
        # Check if required memory exceeds limit
        if required > self.max_memory:
            error_msg = (
                f"Required memory {required / (1024**3):.2f} GB exceeds limit "
                f"{self.max_memory / (1024**3):.2f} GB "
                f"({self.max_memory_ratio:.0%} of total GPU memory)"
            )
            logger.error(error_msg)
            raise MemoryError(error_msg)
        
        # Check current memory usage
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free = mem_info[0]
            
            if required > free:
                error_msg = (
                    f"Required memory {required / (1024**3):.2f} GB exceeds "
                    f"available {free / (1024**3):.2f} GB"
                )
                logger.error(error_msg)
                raise MemoryError(error_msg)
            
            # Allocate array using CuPy (which uses the memory pool)
            array = cp.zeros(shape, dtype=dtype)
            
            logger.debug(
                f"Allocated {required / (1024**3):.2f} GB GPU memory "
                f"(shape: {shape}, dtype: {dtype})"
            )
            
            return array
        except cp.cuda.memory.OutOfMemoryError as e:
            error_msg = (
                f"GPU out of memory: required {required / (1024**3):.2f} GB, "
                f"available {free / (1024**3):.2f} GB"
            )
            logger.error(error_msg)
            raise MemoryError(error_msg) from e
        except Exception as e:
            logger.error(f"Failed to allocate GPU memory: {e}")
            raise RuntimeError(f"Failed to allocate GPU memory: {e}") from e
    
    def free_all_blocks(self) -> None:
        """
        Free all blocks in memory pools.
        
        Physical Meaning:
            Forces freeing of all blocks in GPU memory pools,
            useful for memory cleanup and defragmentation.
        """
        if not self.cuda_available:
            logger.warning("CUDA not available - cannot free GPU memory blocks")
            return
        
        try:
            self.pool.free_all_blocks()
            self.pinned_pool.free_all_blocks()
            logger.info("Freed all GPU memory pool blocks")
        except Exception as e:
            logger.error(f"Failed to free GPU memory blocks: {e}")
    
    def defragment_memory(self) -> None:
        """
        Defragment GPU memory by freeing all blocks and synchronizing.
        
        Physical Meaning:
            Performs GPU memory defragmentation by freeing all memory pool
            blocks and forcing synchronization to ensure complete cleanup.
            This helps prevent OOM errors even when sufficient free memory exists.
        """
        if not self.cuda_available:
            logger.warning("CUDA not available - cannot defragment GPU memory")
            return
        
        try:
            # Free all blocks in memory pools
            self.pool.free_all_blocks()
            self.pinned_pool.free_all_blocks()
            
            # Force synchronization to ensure complete cleanup
            cp.cuda.Stream.null.synchronize()
            
            logger.info("GPU memory defragmentation completed")
        except Exception as e:
            logger.error(f"Failed to defragment GPU memory: {e}")
    
    def get_memory_info(self) -> dict:
        """
        Get memory pool information.
        
        Physical Meaning:
            Returns information about GPU memory pools for monitoring
            and optimization of memory allocation patterns.
            
        Returns:
            dict: Memory pool information including:
                - max_memory: Maximum memory limit in bytes
                - mempool_used: Used memory pool bytes
                - mempool_total: Total memory pool bytes
                - pinned_used: Used pinned memory pool bytes
                - pinned_total: Total pinned memory pool bytes
        """
        if not self.cuda_available:
            return {"error": "CUDA not available"}
        
        try:
            return {
                "max_memory": self.max_memory,
                "max_memory_gb": self.max_memory / (1024**3),
                "mempool_used": self.pool.used_bytes(),
                "mempool_total": self.pool.total_bytes(),
                "pinned_used": self.pinned_pool.used_bytes(),
                "pinned_total": self.pinned_pool.total_bytes(),
            }
        except Exception as e:
            logger.error(f"Failed to get memory pool info: {e}")
            return {"error": str(e)}
    
    def get_available_memory(self) -> int:
        """
        Get available memory for allocation.
        
        Physical Meaning:
            Calculates available GPU memory for allocation based on
            current usage and memory limit.
            
        Returns:
            int: Available memory in bytes.
        """
        if not self.cuda_available:
            return 0
        
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free = mem_info[0]
            
            # Return minimum of free memory and remaining limit
            mempool_used = self.pool.used_bytes()
            remaining_limit = self.max_memory - mempool_used
            
            return min(free, remaining_limit)
        except Exception as e:
            logger.error(f"Failed to get available memory: {e}")
            return 0
    
    def allocate_pinned_memory(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
    ) -> np.ndarray:
        """
        Allocate pinned (page-locked) memory for efficient CPU↔GPU transfers.
        
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
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - cannot allocate pinned memory")
        
        try:
            # Calculate required memory
            required = int(np.prod(shape) * np.dtype(dtype).itemsize)
            
            # Allocate pinned memory using CuPy pinned memory pool
            # Pinned memory is allocated as a memoryview that can be used with numpy
            pinned_mem = cp.cuda.alloc_pinned_memory(required)
            
            # Create numpy array from pinned memory buffer
            # Use memoryview to create array without copying
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

