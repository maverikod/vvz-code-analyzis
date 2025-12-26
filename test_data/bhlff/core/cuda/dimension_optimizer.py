"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Dimension order optimization for 7D field processing.

This module provides dimension order optimization for efficient
processing of 7D fields with optimal memory access patterns.

Physical Meaning:
    Provides dimension order optimization for 7D fields:
    - Optimize dimension processing order for cache efficiency
    - Maximize memory locality for optimal performance
    - Minimize memory bandwidth requirements

Mathematical Foundation:
    Optimizes memory access patterns by processing dimensions
    in order of increasing size to maximize cache hits and
    minimize memory bandwidth requirements.

Example:
    >>> from bhlff.core.cuda.dimension_optimizer import DimensionOptimizer
    >>> optimizer = DimensionOptimizer()
    >>> order = optimizer.optimize_order(shape)
    >>> result = optimizer.process_7d_field(field, operation, order)
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

logger = logging.getLogger(__name__)


class DimensionOptimizer:
    """
    Dimension order optimizer for 7D field processing.
    
    Physical Meaning:
        Provides dimension order optimization for 7D fields to maximize
        memory locality and cache efficiency during processing.
        
    Mathematical Foundation:
        Optimizes memory access patterns by processing dimensions
        in order of increasing size to maximize cache hits and
        minimize memory bandwidth requirements.
    """
    
    def __init__(self):
        """
        Initialize dimension optimizer.
        """
        logger.info("DimensionOptimizer initialized")
    
    def optimize_order(
        self,
        shape: Tuple[int, ...],
    ) -> Tuple[int, ...]:
        """
        Optimize dimension processing order for 7D fields.
        
        Physical Meaning:
            Determines optimal dimension processing order for 7D fields
            to maximize memory locality and cache efficiency.
            
        Mathematical Foundation:
            Optimizes memory access patterns by processing dimensions
            in order of increasing size to maximize cache hits and
            minimize memory bandwidth requirements.
            
        Args:
            shape (Tuple[int, ...]): Field shape (7D).
            
        Returns:
            Tuple[int, ...]: Optimized dimension order (indices).
        """
        if len(shape) != 7:
            logger.warning(f"Expected 7D shape, got {len(shape)}D, returning default order")
            return tuple(range(len(shape)))
        
        # Sort dimensions by size (smallest first) for optimal cache usage
        # This maximizes cache hits by processing smaller dimensions first
        dimension_sizes = [(i, shape[i]) for i in range(7)]
        dimension_sizes.sort(key=lambda x: x[1])
        
        optimized_order = tuple(i for i, _ in dimension_sizes)
        
        logger.debug(
            f"Optimized dimension order: {optimized_order} "
            f"(original: {tuple(range(7))}, sizes: {shape})"
        )
        
        return optimized_order
    
    def process_7d_field(
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
        if field.ndim != 7:
            raise ValueError(f"Expected 7D field, got {field.ndim}D")
        
        if dimension_order is None:
            dimension_order = self.optimize_order(field.shape)
        
        result = field.copy()
        
        # Process dimensions in optimized order
        for dim in dimension_order:
            result = operation(result, axis=dim)
        
        return result

