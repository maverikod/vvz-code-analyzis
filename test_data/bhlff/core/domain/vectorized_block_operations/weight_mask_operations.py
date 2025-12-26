"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Weight mask operations for block merging with overlap handling.

This module provides methods for creating weight masks for overlap handling
when merging blocks in 7D fields.
"""

import logging
from typing import Tuple
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..block_processor import BlockInfo

logger = logging.getLogger(__name__)


class WeightMaskOperations:
    """
    Weight mask operations for block merging with overlap handling.
    
    Physical Meaning:
        Provides methods for creating weight masks for overlap handling
        when merging blocks in 7D phase fields.
    """
    
    @staticmethod
    def create_weight_mask_cuda(
        block_info: BlockInfo,
        domain_shape: Tuple[int, ...],
        overlap: int,
        dtype: np.dtype = np.complex128,
    ) -> "cp.ndarray":
        """
        Create weight mask for overlap handling on GPU.
        
        Physical Meaning:
            Creates weight mask for overlap handling when merging blocks,
            ensuring proper weighting at boundaries.
            
        Args:
            block_info (BlockInfo): Block information.
            domain_shape (Tuple[int, ...]): Shape of 7D domain.
            overlap (int): Overlap size.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            cp.ndarray: Weight mask on GPU.
        """
        block_shape = block_info.shape
        weight_mask = cp.ones(block_shape, dtype=cp.float64)
        
        # Apply overlap weights at boundaries using vectorized operations
        for dim in range(len(domain_shape)):
            if block_info.start_indices[dim] > 0 and overlap > 0:
                # Overlap at start
                overlap_size = min(overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(0, overlap_size) if i == dim else slice(None)
                        for i in range(len(domain_shape))
                    )
                ] *= 0.5
            
            if (
                block_info.end_indices[dim] < domain_shape[dim]
                and overlap > 0
            ):
                # Overlap at end
                overlap_size = min(overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(-overlap_size, None) if i == dim else slice(None)
                        for i in range(len(domain_shape))
                    )
                ] *= 0.5
        
        return weight_mask
    
    @staticmethod
    def create_weight_mask_cpu(
        block_info: BlockInfo,
        domain_shape: Tuple[int, ...],
        overlap: int,
        dtype: np.dtype = np.complex128,
    ) -> np.ndarray:
        """
        Create weight mask for overlap handling on CPU.
        
        Physical Meaning:
            Creates weight mask for overlap handling when merging blocks,
            ensuring proper weighting at boundaries.
            
        Args:
            block_info (BlockInfo): Block information.
            domain_shape (Tuple[int, ...]): Shape of 7D domain.
            overlap (int): Overlap size.
            dtype (np.dtype): Data type (default: complex128).
            
        Returns:
            np.ndarray: Weight mask on CPU.
        """
        block_shape = block_info.shape
        weight_mask = np.ones(block_shape, dtype=np.float64)
        
        # Apply overlap weights at boundaries using vectorized operations
        for dim in range(len(domain_shape)):
            if block_info.start_indices[dim] > 0 and overlap > 0:
                # Overlap at start
                overlap_size = min(overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(0, overlap_size) if i == dim else slice(None)
                        for i in range(len(domain_shape))
                    )
                ] *= 0.5
            
            if (
                block_info.end_indices[dim] < domain_shape[dim]
                and overlap > 0
            ):
                # Overlap at end
                overlap_size = min(overlap, block_shape[dim])
                weight_mask[
                    tuple(
                        slice(-overlap_size, None) if i == dim else slice(None)
                        for i in range(len(domain_shape))
                    )
                ] *= 0.5
        
        return weight_mask

