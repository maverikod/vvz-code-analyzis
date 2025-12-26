"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced CUDA features: tensor cores and unified memory support.

This module provides facade for advanced CUDA features including
tensor cores, unified memory, and dimension optimization.

Physical Meaning:
    Provides unified interface for advanced CUDA features:
    - Tensor cores for accelerated matrix operations (if available)
    - Unified memory for simplified memory management
    - Optimized dimension processing order for 7D fields

Mathematical Foundation:
    Implements advanced GPU features for 7D phase field computations:
    - Tensor cores: Accelerate matrix multiplications and convolutions
    - Unified memory: Single memory space accessible from CPU and GPU
    - Dimension ordering: Optimize memory access patterns for 7D fields

Example:
    >>> features = CUDAAdvancedFeatures()
    >>> if features.tensor_cores_available():
    >>>     result = features.compute_with_tensor_cores(field1, field2)
    >>> unified_array = features.allocate_unified_memory(shape, dtype)
"""

import numpy as np
import logging
from typing import Tuple, Optional, Callable

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .tensor_cores import TensorCoreSupport
from .unified_memory import UnifiedMemoryManager
from .dimension_optimizer import DimensionOptimizer

logger = logging.getLogger(__name__)


class CUDAAdvancedFeatures:
    """
    Advanced CUDA features: tensor cores and unified memory.
    
    Physical Meaning:
        Provides unified interface for advanced CUDA features including
        tensor cores (if available), unified memory, and dimension optimization
        for 7D phase field computations.
        
    Mathematical Foundation:
        Implements advanced GPU features:
        - Tensor cores: Accelerate matrix operations using mixed precision
        - Unified memory: Single memory space for CPU-GPU access
        - Dimension ordering: Optimize memory access patterns
        
    Attributes:
        _tensor_support (TensorCoreSupport): Tensor core support.
        _unified_memory (UnifiedMemoryManager): Unified memory manager.
        _dim_optimizer (DimensionOptimizer): Dimension optimizer.
    """
    
    def __init__(self):
        """
        Initialize advanced CUDA features.
        
        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for CUDAAdvancedFeatures. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        self._tensor_support = TensorCoreSupport()
        self._unified_memory = UnifiedMemoryManager()
        self._dim_optimizer = DimensionOptimizer()
        
        logger.info("CUDAAdvancedFeatures initialized")
    
    def tensor_cores_available(self) -> bool:
        """
        Check if tensor cores are available.
        
        Physical Meaning:
            Returns whether tensor cores are available on the GPU
            for accelerated matrix operations.
            
        Returns:
            bool: True if tensor cores are available.
        """
        return self._tensor_support.available()
    
    def compute_capability(self) -> Tuple[int, int]:
        """
        Get GPU compute capability.
        
        Physical Meaning:
            Returns GPU compute capability for feature detection.
            
        Returns:
            Tuple[int, int]: Compute capability (major, minor).
        """
        return self._tensor_support.compute_capability()
    
    def allocate_unified_memory(
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
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            cp.ndarray: Unified memory array.
        """
        return self._unified_memory.allocate(shape, dtype)
    
    def compute_with_tensor_cores(
        self,
        field1: "cp.ndarray",
        field2: "cp.ndarray",
        operation: str = "matmul",
    ) -> "cp.ndarray":
        """
        Compute operation using tensor cores (if available).
        
        Physical Meaning:
            Performs matrix operations using tensor cores for accelerated
            computation. Falls back to standard operations if tensor cores
            are not available.
            
        Args:
            field1 (cp.ndarray): First input field.
            field2 (cp.ndarray): Second input field.
            operation (str): Operation to perform ('matmul', 'conv').
            
        Returns:
            cp.ndarray: Result of operation.
        """
        if operation == "matmul":
            return self._tensor_support.compute_matmul(field1, field2)
        elif operation == "conv":
            return self._tensor_support.compute_conv(field1, field2)
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    def optimize_dimension_order(
        self,
        shape: Tuple[int, ...],
    ) -> Tuple[int, ...]:
        """
        Optimize dimension processing order for 7D fields.
        
        Physical Meaning:
            Determines optimal dimension processing order for 7D fields
            to maximize memory locality and cache efficiency.
            
        Args:
            shape (Tuple[int, ...]): Field shape (7D).
            
        Returns:
            Tuple[int, ...]: Optimized dimension order (indices).
        """
        return self._dim_optimizer.optimize_order(shape)
    
    def process_7d_field_optimized(
        self,
        field: "cp.ndarray",
        operation: Callable,
        dimension_order: Optional[Tuple[int, ...]] = None,
    ) -> "cp.ndarray":
        """
        Process 7D field with optimized dimension order.
        
        Physical Meaning:
            Processes 7D field using optimized dimension order to maximize
            memory locality and cache efficiency.
            
        Args:
            field (cp.ndarray): 7D field on GPU.
            operation (Callable): Operation to perform on each dimension.
            dimension_order (Optional[Tuple[int, ...]]): Dimension order (default: auto).
            
        Returns:
            cp.ndarray: Processed field.
        """
        return self._dim_optimizer.process_7d_field(field, operation, dimension_order)


# Convenience functions
def tensor_cores_available() -> bool:
    """
    Check if tensor cores are available.
    
    Physical Meaning:
        Convenience function to check tensor core availability.
        
    Returns:
        bool: True if tensor cores are available.
    """
    try:
        features = CUDAAdvancedFeatures()
        return features.tensor_cores_available()
    except RuntimeError:
        return False


def allocate_unified_memory(
    shape: Tuple[int, ...],
    dtype: np.dtype = np.complex128,
) -> "cp.ndarray":
    """
    Allocate unified memory accessible from both CPU and GPU.
    
    Physical Meaning:
        Convenience function for unified memory allocation.
        
    Args:
        shape (Tuple[int, ...]): Array shape.
        dtype (np.dtype): Data type (default: complex128).
        
    Returns:
        cp.ndarray: Unified memory array.
    """
    features = CUDAAdvancedFeatures()
    return features.allocate_unified_memory(shape, dtype)


def optimize_dimension_order(
    shape: Tuple[int, ...],
) -> Tuple[int, ...]:
    """
    Optimize dimension processing order for 7D fields.
    
    Physical Meaning:
        Convenience function for dimension order optimization.
        
    Args:
        shape (Tuple[int, ...]): Field shape (7D).
        
    Returns:
        Tuple[int, ...]: Optimized dimension order.
    """
    features = CUDAAdvancedFeatures()
    return features.optimize_dimension_order(shape)
