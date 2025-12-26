"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block processing for transmission matrix computation.

This module provides block processing methods for computing transmission
matrices for large frequency arrays, respecting 80% GPU memory limit.

Physical Meaning:
    Computes transmission matrices T_total(ω) for large frequency arrays
    using block processing that respects 80% GPU memory limit, processing
    frequencies in batches for optimal GPU utilization while maintaining
    vectorized operations within each block.

Mathematical Foundation:
    For each frequency ω_i:
    T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i)
    Processes frequencies in blocks to maximize GPU memory efficiency
    while maintaining vectorized batched matrix multiplication within
    each block.
"""

import numpy as np
from typing import List, Any
import logging

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..abcd import ResonatorLayer
from bhlff.core.bvp import BVPCore


class TransmissionBlockedComputation:
    """
    Block processing for transmission matrix computation.
    
    Physical Meaning:
        Provides block processing methods for computing transmission
        matrices for large frequency arrays.
    """
    
    def __init__(
        self,
        bvp_core: BVPCore = None,
        compute_layer_matrices_vectorized: Any = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize blocked computation.
        
        Args:
            bvp_core (BVPCore): BVP core for 7D domain information.
            compute_layer_matrices_vectorized (callable): Function to compute
                layer matrices vectorized.
            logger (logging.Logger): Logger instance.
        """
        self.bvp_core = bvp_core
        self.compute_layer_matrices_vectorized = compute_layer_matrices_vectorized
        self.logger = logger or logging.getLogger(__name__)
    
    def compute_transmission_matrices_blocked(
        self,
        frequencies: np.ndarray,
        resonators: List[ResonatorLayer],
        use_cuda_flag: bool,
        xp: Any,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute transmission matrices for large frequency arrays using block processing.
        
        Physical Meaning:
            Computes transmission matrices T_total(ω) for large frequency arrays
            using block processing that respects 80% GPU memory limit, processing
            frequencies in batches for optimal GPU utilization while maintaining
            vectorized operations within each block.
            
        Args:
            frequencies (np.ndarray): Array of frequencies.
            resonators (List[ResonatorLayer]): List of resonator layers.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.
            
        Returns:
            np.ndarray: Array of 2x2 transmission matrices.
        """
        n_freqs = len(frequencies)
        
        # Compute optimal batch size for 80% GPU memory usage
        batch_size = self._compute_batch_size(use_cuda_flag, n_freqs)
        
        # Initialize result array
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total_stack = cp.zeros((n_freqs, 2, 2), dtype=cp.complex128)
            # Initialize with identity matrices
            for i in range(n_freqs):
                T_total_stack[i] = cp.eye(2, dtype=cp.complex128)
        else:
            T_total_stack = np.zeros((n_freqs, 2, 2), dtype=np.complex128)
            # Initialize with identity matrices
            for i in range(n_freqs):
                T_total_stack[i] = np.eye(2, dtype=np.complex128)
        
        # Process frequencies in batches
        for i in range(0, n_freqs, batch_size):
            batch_end = min(i + batch_size, n_freqs)
            batch_freqs = frequencies[i:batch_end]
            
            # Initialize batch stack with identity matrices
            if use_cuda_flag and CUDA_AVAILABLE:
                T_batch = cp.stack([cp.eye(2, dtype=cp.complex128)] * len(batch_freqs))
            else:
                T_batch = np.stack([np.eye(2, dtype=np.complex128)] * len(batch_freqs))
            
            # Vectorized matrix multiplication for all layers
            for layer in resonators:
                # Compute layer matrices for batch frequencies
                T_layer_batch = self.compute_layer_matrices_vectorized(
                    layer, batch_freqs, xp, compute_7d_wave_number
                )
                
                # Batched matrix multiplication
                if use_cuda_flag and CUDA_AVAILABLE:
                    T_batch = cp.einsum("ijk,ikl->ijl", T_batch, T_layer_batch)
                else:
                    for j in range(len(batch_freqs)):
                        T_batch[j] = T_batch[j] @ T_layer_batch[j]
            
            # Store batch results
            T_total_stack[i:batch_end] = T_batch
            
            # Periodic memory cleanup for GPU
            if use_cuda_flag and CUDA_AVAILABLE:
                if (i // batch_size) % 4 == 0:
                    cp.get_default_memory_pool().free_all_blocks()
        
        # Convert back to numpy if using CUDA
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total_stack = cp.asnumpy(T_total_stack)
        
        return T_total_stack
    
    def _compute_batch_size(self, use_cuda_flag: bool, n_freqs: int) -> int:
        """
        Compute optimal batch size for block processing.
        
        Physical Meaning:
            Calculates batch size using 7D block tiling when available,
            or standard memory estimation method otherwise.
            
        Args:
            use_cuda_flag (bool): Whether CUDA is available.
            n_freqs (int): Number of frequencies.
            
        Returns:
            int: Batch size for block processing.
        """
        # Try to use 7D block tiling if BVP core is available
        if use_cuda_flag and CUDA_AVAILABLE and self.bvp_core is not None:
            try:
                from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps
                
                domain = self.bvp_core.domain
                if hasattr(domain, "dimensions") and domain.dimensions == 7:
                    # Use 7D block tiling for optimal batch size
                    ops_7d = CUDABackend7DOps()
                    # Estimate field shape: treat each frequency as a 7D point
                    field_shape = domain.shape if hasattr(domain, "shape") else (
                        8, 8, 8, 8, 8, 8, n_freqs
                    )
                    block_tiling = ops_7d.compute_optimal_block_tiling_7d(
                        field_shape=field_shape,
                        dtype=np.complex128,
                        memory_fraction=0.8,  # 80% GPU memory
                        overhead_factor=10.0,  # Overhead for batched operations
                    )
                    # Use minimum block size from tiling as batch size guide
                    optimal_batch_size = min(block_tiling)
                    # Limit to reasonable range
                    batch_size = min(max(optimal_batch_size, 64), 512)
                    self.logger.debug(
                        f"Using 7D block tiling for transmission matrices: "
                        f"batch_size={batch_size}"
                    )
                    return batch_size
            except Exception as e:
                self.logger.debug(
                    f"7D block tiling calculation failed: {e}, using standard method"
                )
        
        # Standard batch size calculation
        return self._compute_standard_batch_size(use_cuda_flag)
    
    def _compute_standard_batch_size(self, use_cuda_flag: bool) -> int:
        """
        Compute standard batch size for block processing.
        
        Physical Meaning:
            Calculates batch size using standard memory estimation method
            when 7D block tiling is not available.
            
        Args:
            use_cuda_flag (bool): Whether CUDA is available.
            
        Returns:
            int: Batch size for block processing.
        """
        if use_cuda_flag and CUDA_AVAILABLE:
            # Estimate memory per frequency: 2x2 complex128 matrix = 128 bytes
            # Overhead factor: ~10x for batched operations and intermediate results
            bytes_per_freq = 128 * 10
            mem_info = cp.cuda.runtime.memGetInfo()
            available_memory = int(mem_info[0] * 0.8)  # 80% limit
            max_batch_size = max(1, available_memory // bytes_per_freq)
            # Limit batch size for reasonable processing
            return min(max_batch_size, 512)
        else:
            return 128  # CPU batch size

