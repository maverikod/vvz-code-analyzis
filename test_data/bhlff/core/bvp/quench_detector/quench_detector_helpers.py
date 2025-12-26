"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for quench detector.

This module provides helper methods as a mixin class.
"""

import numpy as np
from typing import List, Tuple

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchDetectorHelpersMixin:
    """Mixin providing helper methods."""
    
    def _compute_optimal_block_size_from_gpu_memory(self) -> int:
        """
        Compute optimal block size based on available GPU memory.
        
        Physical Meaning:
            Calculates the maximum block size that can fit in 80% of available
            GPU memory, ensuring efficient memory usage while avoiding OOM.
            
        Returns:
            int: Optimal block size for 7D processing.
        """
        if not self.cuda_available:
            return 8  # Default small size for CPU
        
        try:
            from ...utils.cuda_utils import calculate_optimal_window_memory
            
            # For 7D array, we need space for:
            # - Input field
            # - Amplitude computation
            # - Gradient computation (7 gradients)
            # - Morphology operations
            # - Connected components
            # Total overhead factor ~10x
            overhead_factor = 10
            
            max_window_elements, _, _ = calculate_optimal_window_memory(
                gpu_memory_ratio=0.8,
                overhead_factor=overhead_factor,
                logger=self.logger,
            )
            
            # For 7D, calculate block size per dimension
            # Assuming roughly equal dimensions
            elements_per_dim = int(max_window_elements ** (1 / 7))
            
            # Ensure reasonable bounds
            block_size = max(4, min(elements_per_dim, 64))  # Between 4 and 64
            
            self.logger.info(f"Optimal block size: {block_size}")
            
            return block_size
            
        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size: {e}, using default 8"
            )
            return 8
    
    def _iter_block_slices(self, shape: Tuple[int, ...]) -> List[Tuple[slice, ...]]:
        """Generate overlapping block slices for a 7D array."""
        sizes = [self.block_size] * len(shape)
        step = [max(1, s - self.overlap) for s in sizes]
        indices = []
        for dim, dim_len in enumerate(shape):
            pos = 0
            dim_slices = []
            while pos < dim_len:
                end = min(pos + sizes[dim], dim_len)
                start = max(0, end - sizes[dim]) if end == dim_len else pos
                dim_slices.append((start, end))
                if end == dim_len:
                    break
                pos += step[dim]
            indices.append(dim_slices)
        
        # Cartesian product of per-dimension slices
        from itertools import product
        
        blocks: List[Tuple[slice, ...]] = []
        for combo in product(*indices):
            slices = tuple(slice(s, e) for (s, e) in combo)
            blocks.append(slices)
        return blocks
    
    def _validate_thresholds(self) -> None:
        """
        Validate threshold parameters.
        
        Physical Meaning:
            Ensures that threshold parameters are physically reasonable
            and consistent with the BVP theory.
            
        Raises:
            ValueError: If thresholds are invalid.
        """
        if self.amplitude_threshold <= 0:
            raise ValueError("Amplitude threshold must be positive")
        
        if self.detuning_threshold <= 0:
            raise ValueError("Detuning threshold must be positive")
        
        if self.gradient_threshold <= 0:
            raise ValueError("Gradient threshold must be positive")
        
        if self.carrier_frequency <= 0:
            raise ValueError("Carrier frequency must be positive")

