"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized block operations for efficient block extraction and merging.

This module provides vectorized operations for extracting and merging blocks
from 7D fields using advanced indexing and CUDA kernels for optimal performance.

Physical Meaning:
    Provides vectorized operations for block processing in 7D space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, enabling efficient extraction and merging of
    multiple blocks simultaneously using GPU acceleration.

Mathematical Foundation:
    For 7D field with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Vectorized extraction: extracts multiple blocks in parallel
    - Vectorized merging: merges multiple blocks with overlap handling
    - Uses advanced indexing and CUDA kernels for optimal performance

Example:
    >>> from bhlff.core.domain.vectorized_block_operations import VectorizedBlockOperations
    >>> ops = VectorizedBlockOperations(domain_shape)
    >>> blocks = ops.extract_blocks_vectorized(field, block_indices)
    >>> merged = ops.merge_blocks_vectorized(blocks, block_indices)
"""

import logging
from typing import List, Tuple, Optional, Union
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..block_processor import BlockInfo
from .weight_mask_operations import WeightMaskOperations

logger = logging.getLogger(__name__)


class VectorizedBlockOperations:
    """
    Vectorized block operations for efficient block extraction and merging.
    
    Physical Meaning:
        Provides vectorized operations for block processing in 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, enabling efficient extraction and merging of
        multiple blocks simultaneously using GPU acceleration.
        
    Mathematical Foundation:
        For 7D field with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Vectorized extraction: extracts multiple blocks in parallel
        - Vectorized merging: merges multiple blocks with overlap handling
        - Uses advanced indexing and CUDA kernels for optimal performance
        
    Attributes:
        domain_shape (Tuple[int, ...]): Shape of 7D domain.
        dtype (np.dtype): Data type for computations.
        cuda_available (bool): Whether CUDA is available.
    """
    
    def __init__(
        self,
        domain_shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
    ):
        """
        Initialize vectorized block operations.
        
        Physical Meaning:
            Sets up vectorized block operations for efficient processing
            of 7D phase fields.
            
        Args:
            domain_shape (Tuple[int, ...]): Shape of 7D domain.
            dtype (np.dtype): Data type for computations (default: complex128).
        """
        self.domain_shape = domain_shape
        self.dtype = dtype
        self.cuda_available = CUDA_AVAILABLE
        
        logger.info(
            f"VectorizedBlockOperations initialized for domain {domain_shape} "
            f"with CUDA={self.cuda_available}"
        )
    
    def extract_blocks_vectorized(
        self,
        field: Union[np.ndarray, "cp.ndarray"],
        block_indices: List[BlockInfo],
    ) -> List[Union[np.ndarray, "cp.ndarray"]]:
        """
        Extract multiple blocks from field using vectorized operations.
        
        Physical Meaning:
            Extracts multiple blocks from 7D field simultaneously using
            vectorized operations for optimal performance.
            
        Args:
            field (Union[np.ndarray, cp.ndarray]): 7D field to extract blocks from.
            block_indices (List[BlockInfo]): List of block information.
            
        Returns:
            List[Union[np.ndarray, cp.ndarray]]: List of extracted blocks.
        """
        if not block_indices:
            return []
        
        # Use CUDA if available and field is on GPU
        if self.cuda_available and isinstance(field, cp.ndarray):
            return self._extract_blocks_cuda_vectorized(field, block_indices)
        else:
            return self._extract_blocks_cpu_vectorized(field, block_indices)
    
    def merge_blocks_vectorized(
        self,
        blocks: List[Union[np.ndarray, "cp.ndarray"]],
        block_indices: List[BlockInfo],
        overlap: int = 0,
    ) -> Union[np.ndarray, "cp.ndarray"]:
        """
        Merge multiple blocks into full field using vectorized operations.
        
        Physical Meaning:
            Merges multiple blocks back into full 7D field with overlap
            handling using vectorized operations for optimal performance.
            
        Args:
            blocks (List[Union[np.ndarray, cp.ndarray]]): List of blocks to merge.
            block_indices (List[BlockInfo]): List of block information.
            overlap (int): Overlap size for boundary handling (default: 0).
            
        Returns:
            Union[np.ndarray, cp.ndarray]: Merged full field.
        """
        if not blocks or not block_indices:
            if self.cuda_available:
                return cp.zeros(self.domain_shape, dtype=self.dtype)
            else:
                return np.zeros(self.domain_shape, dtype=self.dtype)
        
        # Use CUDA if available and blocks are on GPU
        if self.cuda_available and isinstance(blocks[0], cp.ndarray):
            return self._merge_blocks_cuda_vectorized(blocks, block_indices, overlap)
        else:
            return self._merge_blocks_cpu_vectorized(blocks, block_indices, overlap)
    
    def _extract_blocks_cuda_vectorized(
        self,
        field: "cp.ndarray",
        block_indices: List[BlockInfo],
    ) -> List["cp.ndarray"]:
        """
        Extract blocks using CUDA vectorized operations.
        
        Physical Meaning:
            Extracts multiple blocks from GPU field simultaneously using
            advanced indexing and vectorized operations.
            
        Args:
            field (cp.ndarray): GPU field to extract blocks from.
            block_indices (List[BlockInfo]): List of block information.
            
        Returns:
            List[cp.ndarray]: List of extracted blocks on GPU.
        """
        blocks = []
        
        # Vectorized extraction using advanced indexing
        for block_info in block_indices:
            start_indices = block_info.start_indices
            end_indices = block_info.end_indices
            
            # Create slices for all dimensions
            slices = tuple(
                slice(start, end) for start, end in zip(start_indices, end_indices)
            )
            
            # Extract block using vectorized slicing
            block = field[slices].copy()  # Copy to avoid view issues
            blocks.append(block)
        
        return blocks
    
    def _extract_blocks_cpu_vectorized(
        self,
        field: np.ndarray,
        block_indices: List[BlockInfo],
    ) -> List[np.ndarray]:
        """
        Extract blocks using CPU vectorized operations.
        
        Physical Meaning:
            Extracts multiple blocks from CPU field simultaneously using
            advanced indexing and vectorized operations.
            
        Args:
            field (np.ndarray): CPU field to extract blocks from.
            block_indices (List[BlockInfo]): List of block information.
            
        Returns:
            List[np.ndarray]: List of extracted blocks on CPU.
        """
        blocks = []
        
        # Vectorized extraction using advanced indexing
        for block_info in block_indices:
            start_indices = block_info.start_indices
            end_indices = block_info.end_indices
            
            # Create slices for all dimensions
            slices = tuple(
                slice(start, end) for start, end in zip(start_indices, end_indices)
            )
            
            # Extract block using vectorized slicing
            block = field[slices].copy()  # Copy to avoid view issues
            blocks.append(block)
        
        return blocks
    
    def _merge_blocks_cuda_vectorized(
        self,
        blocks: List["cp.ndarray"],
        block_indices: List[BlockInfo],
        overlap: int,
    ) -> "cp.ndarray":
        """
        Merge blocks using CUDA vectorized operations.
        
        Physical Meaning:
            Merges multiple blocks into full GPU field with overlap handling
            using vectorized operations for optimal performance.
            
        Args:
            blocks (List[cp.ndarray]): List of blocks on GPU to merge.
            block_indices (List[BlockInfo]): List of block information.
            overlap (int): Overlap size for boundary handling.
            
        Returns:
            cp.ndarray: Merged full field on GPU.
        """
        # Initialize result array on GPU
        result = cp.zeros(self.domain_shape, dtype=self.dtype)
        weight_map = cp.zeros(self.domain_shape, dtype=cp.float64)
        
        # Merge blocks with overlap handling using vectorized operations
        for block, block_info in zip(blocks, block_indices):
            start_indices = block_info.start_indices
            end_indices = block_info.end_indices
            
            # Create slices for all dimensions
            slices = tuple(
                slice(start, end) for start, end in zip(start_indices, end_indices)
            )
            
            # Create weight mask for overlap handling
            weight_mask = WeightMaskOperations.create_weight_mask_cuda(
                block_info, self.domain_shape, overlap, self.dtype
            )
            
            # Add block data to result using vectorized operations
            result[slices] += block * weight_mask
            weight_map[slices] += weight_mask
        
        # Normalize by weights using vectorized operations
        result = cp.divide(
            result, weight_map, out=cp.zeros_like(result), where=weight_map != 0
        )
        
        return result
    
    def _merge_blocks_cpu_vectorized(
        self,
        blocks: List[np.ndarray],
        block_indices: List[BlockInfo],
        overlap: int,
    ) -> np.ndarray:
        """
        Merge blocks using CPU vectorized operations.
        
        Physical Meaning:
            Merges multiple blocks into full CPU field with overlap handling
            using vectorized operations for optimal performance.
            
        Args:
            blocks (List[np.ndarray]): List of blocks on CPU to merge.
            block_indices (List[BlockInfo]): List of block information.
            overlap (int): Overlap size for boundary handling.
            
        Returns:
            np.ndarray: Merged full field on CPU.
        """
        # Initialize result array
        result = np.zeros(self.domain_shape, dtype=self.dtype)
        weight_map = np.zeros(self.domain_shape, dtype=np.float64)
        
        # Merge blocks with overlap handling using vectorized operations
        for block, block_info in zip(blocks, block_indices):
            start_indices = block_info.start_indices
            end_indices = block_info.end_indices
            
            # Create slices for all dimensions
            slices = tuple(
                slice(start, end) for start, end in zip(start_indices, end_indices)
            )
            
            # Create weight mask for overlap handling
            weight_mask = WeightMaskOperations.create_weight_mask_cpu(
                block_info, self.domain_shape, overlap, self.dtype
            )
            
            # Add block data to result using vectorized operations
            result[slices] += block * weight_mask
            weight_map[slices] += weight_mask
        
        # Normalize by weights using vectorized operations
        result = np.divide(
            result, weight_map, out=np.zeros_like(result), where=weight_map != 0
        )
        
        return result

