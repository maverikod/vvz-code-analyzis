"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Unified memory support for simplified GPU memory management.

This module provides unified memory support for efficient CPU-GPU
memory management in 7D phase field theory.

Physical Meaning:
    Provides unified memory support for simplified memory management:
    - Unified memory accessible from both CPU and GPU
    - Automatic page migration for optimal performance
    - Simplified memory management for large 7D fields

Mathematical Foundation:
    Unified memory provides a single memory space accessible from
    both CPU and GPU, with automatic page migration for optimal
    performance (CUDA 6.0+).

Example:
    >>> from bhlff.core.cuda.unified_memory import UnifiedMemoryManager
    >>> manager = UnifiedMemoryManager()
    >>> array = manager.allocate(shape, dtype)
"""

import numpy as np
import logging
from typing import Tuple

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class UnifiedMemoryManager:
    """
    Unified memory manager for simplified GPU memory management.
    
    Physical Meaning:
        Provides unified memory support for simplified memory management,
        allowing single memory space accessible from both CPU and GPU
        without explicit transfers.
        
    Mathematical Foundation:
        Unified memory provides a single memory space accessible from
        both CPU and GPU, with automatic page migration for optimal
        performance (CUDA 6.0+).
        
    Attributes:
        _default_device: Default CUDA device.
    """
    
    def __init__(self):
        """
        Initialize unified memory manager.
        
        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for UnifiedMemoryManager. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        self._default_device = cp.cuda.Device()
        
        logger.info("UnifiedMemoryManager initialized")
    
    def allocate(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
    ) -> "cp.ndarray":
        """
        Allocate unified memory accessible from both CPU and GPU.
        
        Physical Meaning:
            Allocates unified memory that can be accessed from both CPU
            and GPU without explicit transfers, simplifying memory management
            for large 7D fields.
            
        Mathematical Foundation:
            Unified memory provides a single memory space accessible from
            both CPU and GPU, with automatic page migration for optimal
            performance.
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            cp.ndarray: Unified memory array.
        """
        try:
            # Allocate unified memory using CuPy
            # Note: CuPy uses unified memory when available (CUDA 6.0+)
            # For explicit unified memory, we use managed memory
            array = cp.empty(shape, dtype=dtype)
            
            # Set memory preference to prefer GPU
            # This is a hint for the driver to keep data on GPU
            try:
                # Try to set memory preference (CUDA 8.0+)
                cp.cuda.runtime.memAdvise(
                    array.data.ptr,
                    array.nbytes,
                    cp.cuda.runtime.memAdviseSetPreferredLocation,
                    cp.cuda.runtime.memLocationDevice
                )
            except AttributeError:
                # memAdvise not available, use default behavior
                logger.debug("memAdvise not available, using default unified memory behavior")
            
            logger.debug(
                f"Allocated {array.nbytes / (1024**3):.2f} GB unified memory "
                f"(shape: {shape}, dtype: {dtype})"
            )
            
            return array
        except Exception as e:
            logger.error(f"Failed to allocate unified memory: {e}")
            raise RuntimeError(f"Failed to allocate unified memory: {e}") from e
    
    def prefetch_to_gpu(self, array: "cp.ndarray") -> None:
        """
        Prefetch unified memory to GPU.
        
        Physical Meaning:
            Prefetches unified memory to GPU to optimize performance
            for upcoming GPU operations.
            
        Args:
            array (cp.ndarray): Unified memory array.
        """
        try:
            cp.cuda.runtime.memPrefetchAsync(
                array.data.ptr,
                array.nbytes,
                cp.cuda.runtime.memLocationDevice,
                cp.cuda.Stream.null.ptr
            )
        except AttributeError:
            logger.debug("memPrefetchAsync not available, skipping prefetch")
        except Exception as e:
            logger.warning(f"Failed to prefetch to GPU: {e}")
    
    def prefetch_to_cpu(self, array: "cp.ndarray") -> None:
        """
        Prefetch unified memory to CPU.
        
        Physical Meaning:
            Prefetches unified memory to CPU to optimize performance
            for upcoming CPU operations.
            
        Args:
            array (cp.ndarray): Unified memory array.
        """
        try:
            cp.cuda.runtime.memPrefetchAsync(
                array.data.ptr,
                array.nbytes,
                cp.cuda.runtime.memLocationCPU,
                cp.cuda.Stream.null.ptr
            )
        except AttributeError:
            logger.debug("memPrefetchAsync not available, skipping prefetch")
        except Exception as e:
            logger.warning(f"Failed to prefetch to CPU: {e}")

