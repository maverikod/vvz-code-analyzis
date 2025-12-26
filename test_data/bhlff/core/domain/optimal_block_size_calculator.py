"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Unified optimal block size calculator for 7D domains.

This module provides a unified interface for calculating optimal block sizes
for 7D phase field computations, ensuring consistent 80% GPU memory usage
across all components.

Physical Meaning:
    Calculates optimal block sizes for 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
    ensuring efficient GPU memory utilization (80% by default) while
    preserving 7D geometric structure.

Mathematical Foundation:
    For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
    - Available memory: gpu_memory_ratio × free GPU memory (default: 80%)
    - Block size per dimension: (available_memory / overhead) ^ (1/7)
    - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)

Example:
    >>> calculator = OptimalBlockSizeCalculator(gpu_memory_ratio=0.8)
    >>> block_size = calculator.calculate_for_7d(domain_shape, dtype=np.complex128)
"""

import numpy as np
import logging
import psutil
from typing import Tuple, Optional
import os

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps

logger = logging.getLogger(__name__)


class OptimalBlockSizeCalculator:
    """
    Unified optimal block size calculator for 7D domains.
    
    Physical Meaning:
        Provides unified interface for calculating optimal block sizes
        for 7D phase field computations, ensuring consistent GPU memory
        usage (80% by default) across all components.
        
    Mathematical Foundation:
        For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
        - Available memory: gpu_memory_ratio × free GPU memory
        - Block size per dimension: (available_memory / overhead) ^ (1/7)
        - Preserves 7D structure: spatial (0,1,2), phase (3,4,5), temporal (6)
        
    Attributes:
        gpu_memory_ratio (float): Fraction of GPU memory to use (default: 0.8).
        _7d_ops (Optional[CUDABackend7DOps]): 7D operations helper for CUDA.
        _last_calculation_cache: Cache for last calculation to enable dynamic adaptation.
    """
    
    def __init__(self, gpu_memory_ratio: float = 0.8):
        """
        Initialize optimal block size calculator.
        
        Physical Meaning:
            Sets up calculator with specified GPU memory ratio for consistent
            block size calculation across all components.
            
        Args:
            gpu_memory_ratio (float): Fraction of GPU memory to use
                (default: 0.8 for 80% usage). Can be overridden via
                BHLFF_GPU_MEMORY_RATIO environment variable.
        """
        # Allow override via environment variable
        ratio_str = os.getenv("BHLFF_GPU_MEMORY_RATIO", str(gpu_memory_ratio))
        try:
            self.gpu_memory_ratio = float(min(max(float(ratio_str), 0.1), 0.95))
        except Exception:
            self.gpu_memory_ratio = gpu_memory_ratio
        
        # Initialize 7D operations helper for CUDA
        self._7d_ops = None
        if CUDA_AVAILABLE:
            try:
                self._7d_ops = CUDABackend7DOps()
            except Exception as e:
                logger.warning(f"Failed to initialize CUDABackend7DOps: {e}")
        
        # Cache for dynamic adaptation
        self._last_calculation_cache = {}
        
        logger.info(
            f"OptimalBlockSizeCalculator initialized with "
            f"gpu_memory_ratio={self.gpu_memory_ratio}"
        )
    
    def calculate_for_7d(
        self,
        domain_shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
        overhead_factor: float = 5.0,
        use_cache: bool = True,
    ) -> Tuple[int, ...]:
        """
        Calculate optimal block size for 7D field.
        
        Physical Meaning:
            Computes optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring specified GPU memory usage
            while preserving 7D geometric structure.
            
        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: gpu_memory_ratio × free GPU memory
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5),
              temporal (6)
            
        Args:
            domain_shape (Tuple[int, ...]): Shape of 7D domain
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
            dtype (np.dtype): Data type (default: complex128).
            overhead_factor (float): Memory overhead factor for operations
                (default: 5.0, can be higher for complex operations).
            use_cache (bool): Whether to use cached result if available
                (default: True). Set False to force recalculation.
                
        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple),
                ensuring each dimension has block size that fits in
                specified GPU memory fraction.
                
        Raises:
            ValueError: If domain_shape is not 7D.
            RuntimeError: If GPU memory calculation fails and CUDA is required.
        """
        if len(domain_shape) != 7:
            raise ValueError(
                f"Expected 7D domain shape, got {len(domain_shape)}D. "
                f"Shape: {domain_shape}"
            )
        
        # Check cache for dynamic adaptation
        cache_key = (domain_shape, dtype, overhead_factor)
        if use_cache and cache_key in self._last_calculation_cache:
            cached_result = self._last_calculation_cache[cache_key]
            # Verify cached result is still valid by checking current GPU memory
            if self._verify_cached_result(cached_result, dtype, overhead_factor):
                logger.debug(f"Using cached block size: {cached_result}")
                return cached_result
        
        # Try CUDA calculation first
        if CUDA_AVAILABLE and self._7d_ops is not None:
            try:
                block_tiling = self._7d_ops.compute_optimal_block_tiling_7d(
                    field_shape=domain_shape,
                    dtype=dtype,
                    memory_fraction=self.gpu_memory_ratio,
                    overhead_factor=overhead_factor,
                )
                # Cache result
                self._last_calculation_cache[cache_key] = block_tiling
                logger.info(
                    f"Optimal 7D block tiling: {block_tiling} "
                    f"(GPU memory ratio: {self.gpu_memory_ratio:.1%})"
                )
                return block_tiling
            except Exception as e:
                logger.warning(
                    f"Failed to compute optimal 7D block tiling with CUDA: {e}, "
                    f"falling back to CPU-based calculation"
                )
        
        # CPU fallback: use system memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        usable_memory_gb = available_memory_gb * self.gpu_memory_ratio
        
        # Memory per element
        bytes_per_element = np.dtype(dtype).itemsize
        
        # Maximum elements per 7D block
        max_elements_per_block = int(
            (usable_memory_gb * 1024**3) / (bytes_per_element * overhead_factor)
        )
        
        # For 7D, calculate block size per dimension
        elements_per_dim = int(max_elements_per_block ** (1.0 / 7.0))
        
        # Ensure reasonable bounds
        min_block_size = 4
        max_block_size = 128
        
        # Create block size tuple (7D: spatial, phase, temporal)
        block_tiling = []
        for i, dim_size in enumerate(domain_shape):
            if i < 3:  # Spatial dimensions (0,1,2)
                # Use larger blocks for spatial dimensions
                block_size = max(
                    min_block_size,
                    min(dim_size, min(max_block_size, max(elements_per_dim, 32)))
                )
            else:  # Phase (3,4,5) and temporal (6) dimensions
                # Use smaller blocks for phase/time dimensions
                block_size = max(
                    min_block_size,
                    min(dim_size, max(elements_per_dim, 16))
                )
            block_tiling.append(block_size)
        
        block_tiling_tuple = tuple(block_tiling)
        
        # Cache result
        self._last_calculation_cache[cache_key] = block_tiling_tuple
        
        logger.info(
            f"Optimal 7D block tiling: {block_tiling_tuple} "
            f"(available memory: {available_memory_gb:.2f} GB, "
            f"ratio: {self.gpu_memory_ratio:.1%})"
        )
        
        return block_tiling_tuple
    
    def calculate_single_block_size(
        self,
        domain_shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
        overhead_factor: float = 5.0,
    ) -> int:
        """
        Calculate single optimal block size (minimum of all dimensions).
        
        Physical Meaning:
            Computes single block size value as minimum of all dimensions,
            useful for components that require uniform block size.
            
        Args:
            domain_shape (Tuple[int, ...]): Shape of domain.
            dtype (np.dtype): Data type (default: complex128).
            overhead_factor (float): Memory overhead factor (default: 5.0).
            
        Returns:
            int: Single optimal block size (minimum of all dimensions).
        """
        block_tiling = self.calculate_for_7d(
            domain_shape, dtype, overhead_factor
        )
        return min(block_tiling)
    
    def _verify_cached_result(
        self,
        cached_result: Tuple[int, ...],
        dtype: np.dtype,
        overhead_factor: float,
    ) -> bool:
        """
        Verify cached result is still valid based on current GPU memory.
        
        Physical Meaning:
            Checks if cached block size is still valid given current
            GPU memory availability, enabling dynamic adaptation.
            
        Args:
            cached_result (Tuple[int, ...]): Cached block size result.
            dtype (np.dtype): Data type.
            overhead_factor (float): Memory overhead factor.
            
        Returns:
            bool: True if cached result is still valid, False otherwise.
        """
        if not CUDA_AVAILABLE:
            return True  # CPU fallback doesn't change frequently
        
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory_bytes = mem_info[0]
            total_memory_bytes = mem_info[1]
            
            # Check if cached result still fits in available memory
            bytes_per_element = np.dtype(dtype).itemsize
            block_memory = np.prod(cached_result) * bytes_per_element * overhead_factor
            available_memory = int(total_memory_bytes * self.gpu_memory_ratio)
            
            # Allow 10% tolerance for memory fluctuations
            return block_memory <= available_memory * 1.1
        except Exception:
            return True  # If check fails, assume cache is valid
    
    def clear_cache(self) -> None:
        """
        Clear calculation cache.
        
        Physical Meaning:
            Clears cached block size calculations, forcing recalculation
            on next call (useful for dynamic adaptation).
        """
        self._last_calculation_cache.clear()
        logger.debug("Block size calculation cache cleared")
    
    def get_memory_info(self) -> dict:
        """
        Get current memory information.
        
        Physical Meaning:
            Returns current GPU and CPU memory information for monitoring
            and debugging block size calculations.
            
        Returns:
            dict: Memory information including GPU and CPU memory stats.
        """
        info = {
            "gpu_memory_ratio": self.gpu_memory_ratio,
            "cuda_available": CUDA_AVAILABLE,
        }
        
        # GPU memory info
        if CUDA_AVAILABLE:
            try:
                mem_info = cp.cuda.runtime.memGetInfo()
                info["gpu"] = {
                    "free_bytes": mem_info[0],
                    "total_bytes": mem_info[1],
                    "used_bytes": mem_info[1] - mem_info[0],
                    "available_for_blocks": int(mem_info[1] * self.gpu_memory_ratio),
                }
            except Exception as e:
                info["gpu"] = {"error": str(e)}
        else:
            info["gpu"] = {"available": False}
        
        # CPU memory info
        try:
            cpu_mem = psutil.virtual_memory()
            info["cpu"] = {
                "total_bytes": cpu_mem.total,
                "available_bytes": cpu_mem.available,
                "used_bytes": cpu_mem.used,
                "available_for_blocks": int(cpu_mem.available * self.gpu_memory_ratio),
            }
        except Exception as e:
            info["cpu"] = {"error": str(e)}
        
        return info


def get_default_block_calculator(gpu_memory_ratio: float = 0.8) -> OptimalBlockSizeCalculator:
    """
    Get default block size calculator with configured GPU memory ratio.
    
    Physical Meaning:
        Returns a configured OptimalBlockSizeCalculator instance with
        specified GPU memory ratio (default: 80%) for consistent block
        size calculation across all components.
        
    Mathematical Foundation:
        Provides unified interface for calculating optimal block sizes
        for 7D phase field computations, ensuring consistent GPU memory
        usage across generators, solvers, and analyzers.
        
    Args:
        gpu_memory_ratio (float): Fraction of GPU memory to use
            (default: 0.8 for 80% usage). Can be overridden via
            BHLFF_GPU_MEMORY_RATIO environment variable.
            
    Returns:
        OptimalBlockSizeCalculator: Configured calculator instance.
        
    Example:
        >>> calculator = get_default_block_calculator()
        >>> block_size = calculator.calculate_for_7d(domain_shape)
    """
    return OptimalBlockSizeCalculator(gpu_memory_ratio=gpu_memory_ratio)

