"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block-based CUDA processing for admittance computation with 7D geometry preservation.

This module provides block-based CUDA processing methods for admittance computation,
preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ through optimal block tiling and
axis-wise reductions.

Physical Meaning:
    Provides block-based processing for admittance computation that preserves
    7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, performing axis-wise reductions on GPU
    without flattening. Supports both single-frequency and multi-frequency processing.

Mathematical Foundation:
    Processes 7D blocks with shape determined by optimal tiling, performing
    reductions along all axes to compute:
    - Single frequency: Y(ω) = Σ a*(x,φ,t) s(x,φ,t) / Σ |a(x,φ,t)|²
    - Multiple frequencies: vectorized computation preserving 7D structure

Example:
    >>> processor = AdmittanceBlockProcessing(reductions)
    >>> admittance = processor.compute_blocked_cuda(
    ...     field_gpu, source_gpu, omega, domain, block_tiling
    ... )
"""

import numpy as np
import logging
from typing import Dict, Any, Tuple

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class AdmittanceBlockProcessing:
    """
    Block-based CUDA processing for admittance computation with 7D geometry.

    Physical Meaning:
        Provides block-based processing for admittance computation that preserves
        7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, performing axis-wise reductions on GPU
        without flattening.

    Mathematical Foundation:
        Processes 7D blocks with shape determined by optimal tiling, performing
        reductions along all axes to compute admittance Y(ω) = I(ω)/V(ω).

    Attributes:
        reductions (AdmittanceReductions): Reduction operations instance.
        logger (logging.Logger): Logger instance.
    """

    def __init__(self, reductions: Any):
        """
        Initialize block processing operations.

        Physical Meaning:
            Sets up block processing with reduction operations for 7D geometry-preserving
            admittance computation on GPU.

        Args:
            reductions (AdmittanceReductions): Reduction operations instance.
        """
        self.reductions = reductions
        self.logger = logging.getLogger(__name__)

    def compute_blocked_cuda(
        self,
        field_gpu: "cp.ndarray",
        source_gpu: "cp.ndarray",
        omega: float,
        domain: Dict[str, Any],
        block_tiling: Tuple[int, ...],
    ) -> "cp.ndarray":
        """
        Compute admittance for single frequency using 7D block-preserving CUDA processing.

        Physical Meaning:
            Computes admittance Y(ω) using block-based processing that preserves
            7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, performing axis-wise reductions
            on GPU without flattening. All operations are fully vectorized on GPU
            with explicit stream synchronization for maximum efficiency.

        Mathematical Foundation:
            Processes 7D blocks with shape determined by optimal tiling,
            performing axis-wise reductions along all 7 dimensions to compute:
            numerator = Σ_{all 7D axes} a*(x,φ,t) s(x,φ,t) over all 7D blocks
            denominator = Σ_{all 7D axes} |a(x,φ,t)|² over all 7D blocks
            All reductions use cp.sum() with sequential axis reductions, never
            flattening the array structure, preserving 7D geometry throughout.

        Args:
            field_gpu (cp.ndarray): 7D phase field on GPU with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            source_gpu (cp.ndarray): 7D source field on GPU with same shape.
            omega (float): Frequency ω.
            domain (Dict[str, Any]): Domain parameters.
            block_tiling (Tuple[int, ...]): Optimal 7D block tiling per dimension.

        Returns:
            cp.ndarray: Admittance value (complex scalar).

        Raises:
            ValueError: If field is not 7D or block tiling is invalid.
        """
        # Verify 7D structure
        if field_gpu.ndim != 7:
            raise ValueError(
                f"Expected 7D field, got {field_gpu.ndim}D. "
                f"Shape: {field_gpu.shape}"
            )

        if len(block_tiling) != 7:
            raise ValueError(
                f"Block tiling must have 7 dimensions, got {len(block_tiling)}"
            )

        self.logger.debug(
            f"7D block processing: field shape={field_gpu.shape}, "
            f"block tiling={block_tiling}, omega={omega}"
        )

        # Initialize reduction accumulators on GPU
        # Use complex128 for high precision in 7D computations
        numerator_sum = cp.complex128(0.0)
        denominator_sum = cp.complex128(0.0)

        # Get field shape for 7D block iteration
        shape = field_gpu.shape

        # Create explicit CUDA stream for all block operations
        # Use non-default stream for better GPU utilization and overlap
        stream = cp.cuda.Stream()
        stream.use()

        # Pre-compute phase factor if needed (vectorized operation on GPU)
        # For 7D: time is dimension 6, extract time grid if available
        phase_factor = None
        if omega != 0.0:
            t_val = domain.get("t", 0.0)
            # Vectorized phase factor computation on GPU
            phase_factor = cp.exp(1j * omega * t_val)
            stream.synchronize()

        # Process 7D blocks with optimized vectorized batch processing
        # This preserves 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ while maximizing GPU utilization
        # Optimized block iteration order: spatial (0,1,2), phase (3,4,5), temporal (6)
        # Batch multiple blocks for better GPU utilization and reduced synchronization overhead
        # Optimal block processing order maximizes GPU memory coalescing and cache efficiency
        block_count = 0
        
        # Compute optimal batch size for vectorized block processing
        # Balance between GPU occupancy and memory usage (80% rule)
        # Larger batches reduce synchronization overhead but require more memory
        # Adaptive batch size based on block volume and GPU memory constraints
        block_volume = int(np.prod(block_tiling))
        # Compute batch size: aim for ~80% GPU memory usage with vectorized operations
        # Each batch processes multiple blocks simultaneously for maximum GPU utilization
        # Memory per batch: block_volume * bytes_per_element * overhead * batch_size
        bytes_per_element = 16  # complex128
        overhead_per_block = 4  # field_block, source_block, field_abs_sq, correlation
        
        from ....utils.cuda_utils import calculate_optimal_window_memory
        max_window_elements, _, _ = calculate_optimal_window_memory(
            gpu_memory_ratio=0.8,
            overhead_factor=overhead_per_block,
            logger=None,  # Don't log here
        )
        
        max_window_memory = max_window_elements * bytes_per_element
        max_blocks_per_batch = max(
            1,
            min(
                32,
                max_window_memory // (block_volume * bytes_per_element * overhead_per_block)
            )
        )
        batch_size = max(4, min(max_blocks_per_batch, 16))  # Adaptive batch size
        
        # Pre-allocate batch reduction buffers on GPU for vectorized accumulation
        # These buffers store intermediate reduction results for batched processing
        # Vectorized accumulation maximizes GPU utilization with minimal synchronization
        batch_numerator_buffer = cp.zeros(batch_size, dtype=cp.complex128)
        batch_denominator_buffer = cp.zeros(batch_size, dtype=cp.complex128)
        batch_idx = 0
        
        # Optimized nested loop structure for 7D block processing
        # Process blocks in batches to maximize GPU vectorization and occupancy
        # All operations are fully vectorized on GPU, preserving 7D structure
        for i0 in range(0, shape[0], block_tiling[0]):
            i0_end = min(i0 + block_tiling[0], shape[0])
            for i1 in range(0, shape[1], block_tiling[1]):
                i1_end = min(i1 + block_tiling[1], shape[1])
                for i2 in range(0, shape[2], block_tiling[2]):
                    i2_end = min(i2 + block_tiling[2], shape[2])
                    for i3 in range(0, shape[3], block_tiling[3]):
                        i3_end = min(i3 + block_tiling[3], shape[3])
                        for i4 in range(0, shape[4], block_tiling[4]):
                            i4_end = min(i4 + block_tiling[4], shape[4])
                            for i5 in range(0, shape[5], block_tiling[5]):
                                i5_end = min(i5 + block_tiling[5], shape[5])
                                for i6 in range(0, shape[6], block_tiling[6]):
                                    i6_end = min(i6 + block_tiling[6], shape[6])

                                    # Extract 7D block preserving structure (fully vectorized on GPU)
                                    # All block operations are fully vectorized, preserving 7D geometry
                                    # Vectorized block extraction with optimal GPU memory access patterns
                                    # Preserves 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ throughout
                                    with stream:
                                        # Vectorized 7D block slicing preserving all dimensions
                                        # Optimal GPU memory access pattern for 7D blocks (coalesced access)
                                        field_block = field_gpu[
                                            i0:i0_end,
                                            i1:i1_end,
                                            i2:i2_end,
                                            i3:i3_end,
                                            i4:i4_end,
                                            i5:i5_end,
                                            i6:i6_end,
                                        ]
                                        source_block = source_gpu[
                                            i0:i0_end,
                                            i1:i1_end,
                                            i2:i2_end,
                                            i3:i3_end,
                                            i4:i4_end,
                                            i5:i5_end,
                                            i6:i6_end,
                                        ]

                                        # Apply frequency-dependent phase if needed (fully vectorized on GPU)
                                        # Vectorized phase modulation preserving 7D block structure
                                        # Broadcasts phase factor across all 7D dimensions (broadcasting)
                                        if phase_factor is not None:
                                            field_block = field_block * phase_factor

                                        # Compute field amplitude squared and correlation (fully vectorized GPU)
                                        # All operations are fully vectorized, preserving 7D block structure
                                        # Vectorized absolute value and power operations on GPU (element-wise)
                                        field_abs_sq = cp.abs(field_block) ** 2
                                        # Vectorized complex conjugate and multiplication on GPU (element-wise)
                                        correlation = cp.conj(field_block) * source_block

                                    # Perform axis-wise reduction preserving 7D block structure
                                    # Uses optimized 7D reduction path, never flattening
                                    # Reductions are performed on GPU with optimal memory access patterns
                                    # All reductions are axis-wise, preserving 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
                                    block_numerator = self.reductions.axis_wise_reduce(
                                        correlation, preserve_structure=True
                                    )
                                    block_denominator = self.reductions.axis_wise_reduce(
                                        field_abs_sq, preserve_structure=True
                                    )

                                    # Store reduction results in batch buffer for vectorized accumulation
                                    # Vectorized assignment on GPU maximizes throughput
                                    with stream:
                                        batch_numerator_buffer[batch_idx] = block_numerator
                                        batch_denominator_buffer[batch_idx] = block_denominator
                                    batch_idx += 1
                                    block_count += 1

                                    # Clean up intermediate arrays on GPU to free memory
                                    # Explicit cleanup prevents GPU memory fragmentation
                                    # Ensures 80% GPU memory usage rule is maintained
                                    del field_abs_sq, correlation
                                    # Clean up field_block if it was modified with phase factor
                                    # If phase_factor is None, field_block is just a view and doesn't need cleanup
                                    # But if phase_factor was applied, we created a new array that needs cleanup
                                    if phase_factor is not None:
                                        del field_block
                                    # Note: source_block is a view and doesn't need explicit cleanup

                                    # Process batch when buffer is full (vectorized accumulation)
                                    # Vectorized batch processing maximizes GPU utilization
                                    # Reduces synchronization overhead while maintaining correctness
                                    if batch_idx >= batch_size:
                                        # Vectorized batch accumulation on GPU
                                        # Single vectorized sum operation for all blocks in batch
                                        with stream:
                                            batch_numerator_sum = cp.sum(batch_numerator_buffer)
                                            batch_denominator_sum = cp.sum(batch_denominator_buffer)
                                            # Vectorized accumulation into global sums
                                            numerator_sum = numerator_sum + batch_numerator_sum
                                            denominator_sum = denominator_sum + batch_denominator_sum
                                        stream.synchronize()
                                        
                                        # Reset batch buffer for next batch
                                        batch_idx = 0
                                        cp.get_default_memory_pool().free_all_blocks()

                                    # Periodic memory cleanup (every 8 blocks in temporal axis)
                                    # Prevents GPU memory fragmentation during long computations
                                    # Ensures 80% GPU memory usage rule is maintained
                                    if (i6 // block_tiling[6]) % 8 == 0:
                                        cp.get_default_memory_pool().free_all_blocks()
                                        stream.synchronize()
        
        # Process remaining blocks in batch buffer (partial batch)
        # Vectorized accumulation of remaining blocks maximizes GPU utilization
        if batch_idx > 0:
            with stream:
                # Vectorized batch accumulation for remaining blocks
                batch_numerator_sum = cp.sum(batch_numerator_buffer[:batch_idx])
                batch_denominator_sum = cp.sum(batch_denominator_buffer[:batch_idx])
                # Vectorized accumulation into global sums
                numerator_sum = numerator_sum + batch_numerator_sum
                denominator_sum = denominator_sum + batch_denominator_sum
            stream.synchronize()
        
        # Clean up batch buffers
        del batch_numerator_buffer, batch_denominator_buffer

        # Synchronize after all block operations
        stream.synchronize()

        # Compute admittance with vectorized operations on GPU
        with stream:
            if abs(denominator_sum) > 1e-12:
                admittance = numerator_sum / denominator_sum
            else:
                admittance = cp.complex128(0.0)
        stream.synchronize()

        cp.cuda.Stream.null.use()

        self.logger.debug(
            f"7D block processing: {block_count} blocks, admittance={admittance}"
        )

        return admittance

    def compute_all_freqs_cuda(
        self,
        field_gpu: "cp.ndarray",
        source_gpu: "cp.ndarray",
        frequencies: np.ndarray,
        domain: Dict[str, Any],
    ) -> "cp.ndarray":
        """
        Compute admittance for all frequencies using fully vectorized CUDA operations.

        Physical Meaning:
            Computes admittance Y(ω) for all frequencies simultaneously using
            fully vectorized GPU operations, preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            with axis-wise reductions and explicit stream synchronization. Delegates to
            AdmittanceVectorizedFreqs for optimal GPU vectorization.

        Args:
            field_gpu (cp.ndarray): 7D phase field on GPU with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            source_gpu (cp.ndarray): 7D source field on GPU with same shape.
            frequencies (np.ndarray): Frequencies ω to compute.
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            cp.ndarray: Admittance values for each frequency (complex array).
        """
        from .admittance_vectorized_freqs import AdmittanceVectorizedFreqs

        vectorized_processor = AdmittanceVectorizedFreqs(self.reductions)
        return vectorized_processor.compute_all_freqs_cuda(
            field_gpu, source_gpu, frequencies, domain
        )
