"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D-specific block tiling for optimal memory usage and performance.

This module provides 7D-specific block tiling that accounts for the
different nature of spatial (x,y,z), phase (φ₁,φ₂,φ₃), and temporal (t)
dimensions in the 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    Implements 7D-specific block tiling that optimizes for the geometric
    structure of 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where:
    - Spatial dimensions (0,1,2): Large blocks for efficient spatial processing
    - Phase dimensions (3,4,5): Medium blocks for phase space operations
    - Temporal dimension (6): Small blocks or full dimension for time evolution

Mathematical Foundation:
    For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Spatial block size: optimized for large spatial operations
    - Phase block size: optimized for phase space operations
    - Temporal block size: optimized for time evolution or full dimension

Example:
    >>> from bhlff.core.domain.seven_d_block_tiling import SevenDBlockTiling
    >>> tiling = SevenDBlockTiling(domain_shape, available_memory)
    >>> block_tiling = tiling.compute_7d_block_tiling()
    
    Note: The module file is named 7d_block_tiling.py, but Python imports
    it as seven_d_block_tiling due to module name restrictions.
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

from .optimal_block_size_calculator import OptimalBlockSizeCalculator
from ...exceptions import CUDANotAvailableError

logger = logging.getLogger(__name__)


class SevenDBlockTiling:
    """
    7D-specific block tiling for optimal memory usage and performance.
    
    Physical Meaning:
        Provides 7D-specific block tiling that optimizes for the geometric
        structure of 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, accounting for
        different nature of spatial, phase, and temporal dimensions.
        
    Mathematical Foundation:
        For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Spatial dimensions (0,1,2): Large blocks
        - Phase dimensions (3,4,5): Medium blocks
        - Temporal dimension (6): Small blocks or full dimension
        
    Attributes:
        domain_shape (Tuple[int, ...]): Shape of 7D domain (7-tuple).
        available_memory (int): Available memory in bytes.
        dtype (np.dtype): Data type for computations.
        _block_size_calculator (OptimalBlockSizeCalculator): Calculator for optimal sizes.
    """
    
    def __init__(
        self,
        domain_shape: Tuple[int, ...],
        available_memory: Optional[int] = None,
        dtype: np.dtype = np.complex128,
    ):
        """
        Initialize 7D block tiling calculator.
        
        Physical Meaning:
            Sets up 7D-specific block tiling calculator with awareness of
            spatial, phase, and temporal dimension characteristics.
            
        Args:
            domain_shape (Tuple[int, ...]): Shape of 7D domain (7-tuple).
            available_memory (Optional[int]): Available memory in bytes.
                If None, automatically calculated from GPU/CPU memory.
            dtype (np.dtype): Data type for computations (default: complex128).
        """
        if len(domain_shape) != 7:
            raise ValueError(
                f"Expected 7D domain shape, got {len(domain_shape)}D. "
                f"Shape: {domain_shape}"
            )
        
        self.domain_shape = domain_shape
        self.dtype = dtype
        
        # Initialize block size calculator
        self._block_size_calculator = OptimalBlockSizeCalculator(gpu_memory_ratio=0.8)
        
        # Calculate available memory if not provided
        if available_memory is None:
            available_memory = self._calculate_available_memory()
        
        self.available_memory = available_memory
        
        logger.info(
            f"SevenDBlockTiling initialized for domain {domain_shape} "
            f"with available memory {available_memory / (1024**3):.2f} GB"
        )
    
    def compute_7d_block_tiling(
        self,
        overhead_factor: float = 5.0,
    ) -> Tuple[int, int, int, int, int, int, int]:
        """
        Compute optimal 7D block tiling.
        
        Physical Meaning:
            Computes optimal block tiling for 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            accounting for different characteristics of spatial, phase, and
            temporal dimensions.
            
        Mathematical Foundation:
            For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Spatial dimensions (0,1,2): Large blocks for efficient spatial processing
            - Phase dimensions (3,4,5): Medium blocks for phase space operations
            - Temporal dimension (6): Small blocks or full dimension for time evolution
            
        Args:
            overhead_factor (float): Memory overhead factor for operations
                (default: 5.0 for complex 7D operations).
                
        Returns:
            Tuple[int, int, int, int, int, int, int]: Block size per dimension
                (spatial, spatial, spatial, phase, phase, phase, temporal).
        """
        # Use unified calculator for base calculation
        base_tiling = self._block_size_calculator.calculate_for_7d(
            domain_shape=self.domain_shape,
            dtype=self.dtype,
            overhead_factor=overhead_factor,
        )
        
        # Adjust for 7D-specific characteristics
        block_tiling = []
        
        for i, (dim_size, base_size) in enumerate(zip(self.domain_shape, base_tiling)):
            if i < 3:  # Spatial dimensions (0,1,2)
                # Use larger blocks for spatial dimensions
                # Spatial operations benefit from larger blocks
                block_size = max(
                    4,  # Minimum block size
                    min(
                        dim_size,  # Don't exceed dimension size
                        max(base_size, 32)  # Prefer larger blocks for spatial
                    )
                )
            elif i < 6:  # Phase dimensions (3,4,5)
                # Use medium blocks for phase dimensions
                # Phase space operations can use medium blocks
                block_size = max(
                    4,  # Minimum block size
                    min(
                        dim_size,  # Don't exceed dimension size
                        max(base_size, 16)  # Medium blocks for phase
                    )
                )
            else:  # Temporal dimension (6)
                # Use smaller blocks or full dimension for temporal
                # Time evolution may benefit from full dimension or small blocks
                block_size = max(
                    4,  # Minimum block size
                    min(
                        dim_size,  # Don't exceed dimension size
                        max(base_size, 8)  # Smaller blocks for temporal
                    )
                )
            
            block_tiling.append(block_size)
        
        block_tiling_tuple = tuple(block_tiling)
        
        logger.info(
            f"7D block tiling: spatial={block_tiling_tuple[:3]}, "
            f"phase={block_tiling_tuple[3:6]}, temporal={block_tiling_tuple[6]}"
        )
        
        return block_tiling_tuple
    
    def get_processing_order(self) -> Tuple[int, ...]:
        """
        Get optimal processing order for 7D dimensions.
        
        Physical Meaning:
            Returns optimal order for processing 7D dimensions based on
            their characteristics: spatial first, then phase, then temporal.
            
        Returns:
            Tuple[int, ...]: Processing order (dimension indices).
        """
        # Process spatial dimensions first (0,1,2)
        # Then phase dimensions (3,4,5)
        # Finally temporal dimension (6)
        return (0, 1, 2, 3, 4, 5, 6)
    
    def _calculate_available_memory(self) -> int:
        """
        Calculate available memory from GPU or CPU.
        
        Physical Meaning:
            Calculates available memory from GPU (if CUDA available) or CPU,
            using 80% of free memory for GPU or configurable fraction for CPU.
            
        Returns:
            int: Available memory in bytes.
        """
        if CUDA_AVAILABLE:
            try:
                mem_info = cp.cuda.runtime.memGetInfo()
                free_memory_bytes = mem_info[0]
                # Use 80% of free GPU memory (project requirement)
                available_memory_bytes = int(free_memory_bytes * 0.8)
                logger.debug(
                    f"GPU memory: free={free_memory_bytes / (1024**3):.2f} GB, "
                    f"available (80%)={available_memory_bytes / (1024**3):.2f} GB"
                )
                return available_memory_bytes
            except Exception as e:
                logger.error(
                    f"Failed to get GPU memory: {e}. CPU fallback is NOT ALLOWED. "
                    "CUDA is required for 7D block tiling."
                )
                raise CUDANotAvailableError(
                    f"Failed to get GPU memory: {e}. CPU fallback is NOT ALLOWED. "
                    "CUDA is required for 7D block tiling. "
                    "Please ensure CUDA is properly configured."
                ) from e
        
        # CUDA is required - no CPU fallback
        logger.error(
            "CUDA is required for 7D block tiling. CPU fallback is NOT ALLOWED."
        )
        raise CUDANotAvailableError(
            "CUDA is required for 7D block tiling. CPU fallback is NOT ALLOWED. "
            "Please install CuPy and ensure CUDA is properly configured."
        )

