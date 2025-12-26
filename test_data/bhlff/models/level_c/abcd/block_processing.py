"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block processing for ABCD admittance computation with 80% GPU memory limit.

This module provides block-based processing for computing admittance for large
frequency arrays, respecting the 80% GPU memory limit and maximizing GPU
utilization through batched processing.

Physical Meaning:
    Implements block processing for admittance computation that respects 80%
    GPU memory limit, processing frequencies in batches for optimal GPU
    utilization while maintaining vectorized operations within each block.

Mathematical Foundation:
    Processes frequencies in blocks to maximize GPU memory efficiency:
    Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
    system transmission matrix at frequency ω. All operations are vectorized
    within each block to maximize GPU utilization.

Example:
    >>> processor = ABCDBlockProcessing()
    >>> admittance = processor.compute_admittance_blocked(
    ...     frequencies_gpu, compute_transmission_matrix, use_cuda_flag, xp
    ... )
"""

import numpy as np
from typing import Any

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class ABCDBlockProcessing:
    """
    Block processing for ABCD admittance computation with 80% GPU memory limit.

    Physical Meaning:
        Provides block-based processing for computing admittance for large
        frequency arrays, respecting the 80% GPU memory limit and maximizing
        GPU utilization through batched processing.

    Mathematical Foundation:
        Processes frequencies in blocks to maximize GPU memory efficiency
        while maintaining vectorized operations within each block.
    """

    @staticmethod
    def compute_admittance_blocked(
        frequencies_gpu: np.ndarray,
        compute_transmission_matrix: Any,
        use_cuda_flag: bool,
        xp: Any,
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using block processing (80% GPU memory).

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for large frequency arrays
            using block processing that respects 80% GPU memory limit,
            processing frequencies in batches for optimal GPU utilization.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω. Processes frequencies
            in blocks to maximize GPU memory efficiency while maintaining
            vectorized operations within each block.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            compute_transmission_matrix (callable): Function to compute transmission matrix.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        n_freqs = len(frequencies_gpu)

        # Compute optimal batch size for 80% GPU memory usage
        if use_cuda_flag and CUDA_AVAILABLE:
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
            T_batch = compute_transmission_matrix(batch_freqs, use_cuda=use_cuda_flag)

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

