"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Admittance computation for ABCD model.

This module implements computation of admittance Y(ω) = C(ω) / A(ω) for
frequency arrays, with vectorized CUDA operations and block processing
for optimal GPU memory usage (80% limit).

Physical Meaning:
    Computes admittance Y(ω) = I(ω)/V(ω) for all frequencies, representing
    the system's response to external excitation using vectorized operations
    and block processing for large frequency arrays.

Mathematical Foundation:
    Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
    system transmission matrix at frequency ω. Processes frequencies
    in blocks to maximize GPU memory efficiency while maintaining
    vectorized operations within each block.

Example:
    >>> from bhlff.models.level_c.abcd_model.admittance_computation import (
    ...     ABCDAdmittanceComputation
    ... )
    >>> computation = ABCDAdmittanceComputation(compute_transmission_matrix)
    >>> admittance = computation.compute_admittance_vectorized(frequencies, ...)
"""

import numpy as np
from typing import Any, Callable, Optional
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class ABCDAdmittanceComputation:
    """
    Admittance computation for ABCD model.

    Physical Meaning:
        Provides methods for computing admittance Y(ω) = C(ω) / A(ω) for
        frequency arrays, with CUDA-accelerated block processing.

    Mathematical Foundation:
        Implements admittance computation with vectorized operations and
        block processing for optimal GPU memory usage.
    """

    def __init__(
        self,
        compute_transmission_matrix: Callable,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize admittance computation.

        Args:
            compute_transmission_matrix (Callable): Function to compute transmission matrix.
            logger (Optional[logging.Logger]): Logger instance.
        """
        self.compute_transmission_matrix = compute_transmission_matrix
        self.logger = logger or logging.getLogger(__name__)

    def compute_admittance_vectorized(
        self, frequencies_gpu: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using vectorized operations.

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for all frequencies
            using vectorized operations, maximizing GPU utilization.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        # Compute transmission matrices for all frequencies at once
        T_stack = self.compute_transmission_matrix(
            frequencies_gpu, use_cuda=use_cuda_flag
        )

        # Extract A and C elements for all frequencies
        A = T_stack[:, 0, 0]
        C = T_stack[:, 1, 0]

        # Vectorized division with zero handling
        admittance = xp.where(xp.abs(A) > 1e-12, C / A, xp.complex128(0.0))

        return admittance

    def compute_admittance_blocked(
        self,
        frequencies_gpu: np.ndarray,
        use_cuda_flag: bool,
        xp: Any,
        optimal_batch_size: Optional[int] = None,
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using block processing (80% GPU memory).

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for large frequency arrays
            using block processing that respects 80% GPU memory limit,
            processing frequencies in batches for optimal GPU utilization.
            Uses 7D-aware block tiling calculation when optimal_batch_size is provided.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω. Processes frequencies
            in blocks to maximize GPU memory efficiency while maintaining
            vectorized operations within each block. Uses 7D block tiling
            from CUDABackend7DOps when available for precise 80% memory calculation.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            optimal_batch_size (Optional[int]): Optimal batch size from 7D block tiling.
                If None, calculates using standard method.

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        n_freqs = len(frequencies_gpu)

        # Compute optimal batch size for 80% GPU memory usage
        if optimal_batch_size is not None:
            # Use provided optimal batch size from 7D block tiling
            batch_size = optimal_batch_size
        elif use_cuda_flag and CUDA_AVAILABLE:
            # Estimate memory per frequency: 2x2 complex128 matrix = 128 bytes
            # Overhead factor: ~5x for intermediate computations
            bytes_per_freq = 128 * 5
            mem_info = cp.cuda.runtime.memGetInfo()
            available_memory = int(mem_info[0] * 0.8)  # 80% limit
            max_batch_size = max(1, available_memory // bytes_per_freq)
            # Limit batch size for reasonable processing
            batch_size = min(max_batch_size, 256)
        else:
            batch_size = 64  # CPU batch size

        # Initialize result array
        admittance = xp.zeros(n_freqs, dtype=xp.complex128)

        # Process frequencies in batches
        for i in range(0, n_freqs, batch_size):
            batch_end = min(i + batch_size, n_freqs)
            batch_freqs = frequencies_gpu[i:batch_end]

            # Compute transmission matrices for batch
            T_batch = self.compute_transmission_matrix(
                batch_freqs, use_cuda=use_cuda_flag
            )

            # Extract A and C elements for batch
            A_batch = T_batch[:, 0, 0]
            C_batch = T_batch[:, 1, 0]

            # Vectorized division with zero handling
            admittance_batch = xp.where(
                xp.abs(A_batch) > 1e-12, C_batch / A_batch, xp.complex128(0.0)
            )

            # Store batch results
            admittance[i:batch_end] = admittance_batch

            # Periodic memory cleanup for GPU
            if use_cuda_flag and CUDA_AVAILABLE:
                if (i // batch_size) % 4 == 0:
                    cp.get_default_memory_pool().free_all_blocks()

        return admittance
