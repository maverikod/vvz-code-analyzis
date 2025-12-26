"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized admittance processor for Level C computations with 7D geometry.

This module provides CUDA-accelerated admittance computation functionality
for Level C boundary analysis with 7D phase field support, optimized block
processing, and GPU memory management preserving 7D structure.

Physical Meaning:
    Computes admittance Y(ω) = I(ω)/V(ω) for boundary analysis in 7D space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, enabling efficient frequency-domain analysis of
    boundary effects while preserving the 7D geometric structure.

Mathematical Foundation:
    Implements admittance computation in 7D:
    Y(ω) = ∫ a*(x,φ,t) s(x,φ,t) dV₇ / ∫ |a(x,φ,t)|² dV₇
    where dV₇ = d³x d³φ dt is the 7D volume element.
    All operations preserve 7D structure with axis-wise reductions.

Theoretical Background:
    The 7D phase field theory operates in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where
    spatial coordinates x ∈ ℝ³, phase coordinates φ ∈ 𝕋³, and time t ∈ ℝ.
    Block processing preserves this structure by computing optimal 7D tiling
    that uses 80% of GPU memory with proper axis-wise reductions.

Example:
    >>> processor = AdmittanceProcessor(backend, block_size)
    >>> admittances = processor.compute_vectorized(field, source, frequencies, domain)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .admittance import (
    AdmittanceReductions,
    AdmittanceBlockProcessing,
    AdmittanceOptimization,
)


class AdmittanceProcessor:
    """
    CUDA-optimized admittance processor for Level C computations with 7D geometry.

    Physical Meaning:
        Provides GPU-accelerated admittance computation for boundary analysis
        in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, preserving 7D geometric structure
        through axis-wise reductions and optimal block tiling.

    Mathematical Foundation:
        Computes admittance Y(ω) = I(ω)/V(ω) using vectorized operations with
        block-preserving reductions that maintain 7D structure. All operations
        use axis-wise reductions on GPU without flattening, ensuring geometric
        consistency in 7D space-time.

    Attributes:
        backend (CUDABackend): CUDA backend for GPU operations.
        block_size (int): Default block size per dimension.
        cuda_available (bool): Whether CUDA is available.
        logger (logging.Logger): Logger instance.
        _optimal_block_tiling (Tuple[int, ...]): Optimal 7D block tiling.
        _reductions (AdmittanceReductions): Reduction operations.
        _block_processing (AdmittanceBlockProcessing): Block processing operations.
        _optimization (AdmittanceOptimization): Optimization operations.
    """

    def __init__(self, backend: Any, block_size: int, cuda_available: bool):
        """
        Initialize admittance processor.

        Physical Meaning:
            Sets up GPU-accelerated admittance processor with 7D geometry support,
            computing optimal block tiling for 80% GPU memory usage.

        Args:
            backend (CUDABackend): CUDA backend for GPU operations.
            block_size (int): Default block size per dimension.
            cuda_available (bool): Whether CUDA is available.
        """
        self.backend = backend
        self.block_size = block_size
        self.cuda_available = cuda_available
        self.logger = logging.getLogger(__name__)
        self._optimal_block_tiling: Optional[Tuple[int, ...]] = None

        # Initialize submodules
        self._reductions = AdmittanceReductions()
        self._block_processing = AdmittanceBlockProcessing(self._reductions)
        self._optimization = AdmittanceOptimization()

    def compute_vectorized(
        self,
        field: np.ndarray,
        source: np.ndarray,
        frequencies: np.ndarray,
        domain: Dict[str, Any],
    ) -> np.ndarray:
        """
        Compute admittance spectrum using vectorized operations.

        Physical Meaning:
            Computes admittance Y(ω) = I(ω)/V(ω) for all frequencies
            using GPU-accelerated vectorized operations.

        Args:
            field (np.ndarray): Field data.
            source (np.ndarray): Source field.
            frequencies (np.ndarray): Frequencies to compute.
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            np.ndarray: Admittance values for each frequency (complex).
        """
        # CUDA is required for Level C - no fallback
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - Level C requires GPU")
        return self._compute_cuda(field, source, frequencies, domain)

    def _compute_cuda(
        self,
        field: np.ndarray,
        source: np.ndarray,
        frequencies: np.ndarray,
        domain: Dict[str, Any],
    ) -> np.ndarray:
        """
        Compute admittance using CUDA acceleration with 7D geometry preservation.

        Physical Meaning:
            Computes admittance Y(ω) = I(ω)/V(ω) in 7D space-time M₇,
            preserving geometric structure through block-preserving reductions
            with optimal GPU memory usage (80%) and explicit stream synchronization.
            All reductions are performed axis-wise on GPU without flattening,
            maintaining 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ throughout.

        Mathematical Foundation:
            Performs axis-wise reductions on GPU without flattening, ensuring
            all operations maintain 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            Uses explicit CUDA stream synchronization for optimal GPU utilization
            and block-preserving reductions that maintain 7D geometric structure.
            All reductions use cp.sum() with sequential axis reductions, never
            flattening the array structure.

        Args:
            field (np.ndarray): 7D phase field a(x,φ,t) with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            source (np.ndarray): 7D source field s(x,φ,t) with same shape.
            frequencies (np.ndarray): Frequencies ω to compute.
            domain (Dict[str, Any]): Domain parameters including spatial,
                phase, and temporal configurations.

        Returns:
            np.ndarray: Admittance values for each frequency (complex array).

        Raises:
            RuntimeError: If CUDA is not available or backend is not CUDA.
            ValueError: If field or source arrays are not 7D.
        """
        # CUDA is required - verify backend is CUDA
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - Level C requires GPU")

        # Verify backend is CUDA (not CPU)
        from bhlff.utils.cuda_utils import CUDABackend

        if not isinstance(self.backend, CUDABackend):
            raise RuntimeError(
                f"Backend is not CUDA! Got {type(self.backend).__name__}. "
                f"Level C requires GPU acceleration."
            )

        # Verify 7D structure
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field, got {field.ndim}D. " f"Shape: {field.shape}"
            )
        if source.ndim != 7:
            raise ValueError(
                f"Expected 7D source, got {source.ndim}D. " f"Shape: {source.shape}"
            )

        # Create explicit CUDA stream for all operations
        # Use non-default stream for better GPU utilization and overlap
        stream = cp.cuda.Stream()
        stream.use()

        self.logger.info(
            f"Computing admittance on GPU: field shape={field.shape}, "
            f"num_frequencies={len(frequencies)}, ndim={field.ndim}"
        )

        # Transfer to GPU with explicit stream synchronization
        # Use pinned memory transfers for better performance
        with stream:
            field_gpu = self.backend.array(field)
            source_gpu = self.backend.array(source)

        # Verify arrays are on GPU
        if not isinstance(field_gpu, cp.ndarray):
            raise RuntimeError(f"Field not on GPU! Type: {type(field_gpu)}")
        if not isinstance(source_gpu, cp.ndarray):
            raise RuntimeError(f"Source not on GPU! Type: {type(source_gpu)}")

        # Synchronize to ensure GPU transfers complete
        stream.synchronize()

        self.logger.info(
            f"Arrays transferred to GPU: field={field_gpu.shape}, "
            f"source={source_gpu.shape}, ndim={field_gpu.ndim}"
        )

        # Compute optimal 7D block tiling for 80% GPU memory
        # This computes optimal tiling per dimension preserving 7D structure
        # Optimized for 7D geometry: spatial (0,1,2), phase (3,4,5), temporal (6)
        block_tiling = self._optimization.compute_optimal_7d_block_tiling(field_gpu)
        self._optimal_block_tiling = block_tiling

        # Check memory requirements before processing
        # Memory overhead for 7D operations with vectorization:
        # - Input field: 1x
        # - Source field: 1x
        # - Field amplitude squared: 1x
        # - Correlation: 1x
        # - Frequency-dependent phase factors: 1x
        # - Intermediate operations: 2x
        # - Reduction buffers (axis-wise, no flatten): 1x
        # - FFT workspace (if needed for 7D operations): 2x
        # Total: ~10x for 7D operations with vectorization
        field_size_bytes = field_gpu.nbytes
        bytes_per_element = 16  # complex128
        overhead_factor = 10
        required_memory = field_size_bytes * overhead_factor

        # Get available GPU memory (80% usage as required)
        mem_info = cp.cuda.runtime.memGetInfo()
        available_memory = mem_info[0]
        safe_memory = int(available_memory * 0.8)  # 80% as required

        self.logger.debug(
            f"Memory check: required={required_memory/1e9:.2f}GB, "
            f"available={safe_memory/1e9:.2f}GB (80% of {available_memory/1e9:.2f}GB), "
            f"block tiling={block_tiling}"
        )

        if required_memory > safe_memory:
            self.logger.info(
                f"Field too large for direct processing: "
                f"{required_memory/1e9:.2f}GB required, "
                f"{safe_memory/1e9:.2f}GB available (80%). "
                f"Using 7D block processing with tiling {block_tiling}."
            )
            # Block-based processing preserving 7D structure
            # Process frequencies with block-preserving axis-wise reductions
            # All reductions performed on GPU without flattening
            # Optimized for maximum GPU utilization with 7D geometry preservation
            num_freqs = len(frequencies)
            admittances_gpu = cp.zeros(num_freqs, dtype=cp.complex128)

            # Process frequencies with optimized batch synchronization
            # Use vectorized operations where possible while preserving 7D structure
            # All reductions are axis-wise, never using flatten()
            # Batch processing maximizes GPU utilization with explicit stream sync
            # Optimal batch size balances memory usage and GPU occupancy
            batch_size = max(4, min(16, num_freqs // 4))  # Adaptive batch size
            for i, omega in enumerate(frequencies):
                # Compute admittance with block-preserving 7D processing
                # All reductions are axis-wise on GPU, preserving 7D structure
                # Uses optimized 7D reduction path for maximum GPU efficiency
                # Explicit stream synchronization ensures proper GPU utilization
                admittance = self._block_processing.compute_blocked_cuda(
                    field_gpu, source_gpu, omega, domain, block_tiling
                )
                with stream:
                    # Vectorized assignment on GPU
                    admittances_gpu[i] = admittance

                # Batch synchronization: synchronize every batch_size frequencies
                # Reduces synchronization overhead while maintaining correctness
                # Explicit stream synchronization for optimal GPU utilization
                if (i + 1) % batch_size == 0:
                    stream.synchronize()

                # Periodic memory cleanup to prevent GPU memory fragmentation
                # Clean every 10 frequencies to balance memory usage with performance
                # Ensures 80% GPU memory usage rule is maintained
                if (i + 1) % 10 == 0:
                    cp.get_default_memory_pool().free_all_blocks()
                    stream.synchronize()
        else:
            # Process all frequencies at once with fully vectorized 7D operations
            # This is more efficient when memory allows, using maximum GPU vectorization
            # All reductions are axis-wise on GPU, preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            # Fully vectorized operations maximize GPU utilization with explicit stream sync
            with stream:
                admittances_gpu = self._block_processing.compute_all_freqs_cuda(
                    field_gpu, source_gpu, frequencies, domain
                )
            # Explicit synchronization after vectorized computation
            stream.synchronize()

        # Final synchronization before transfer
        # Ensures all GPU operations complete before host-device transfer
        stream.synchronize()

        # Transfer back to CPU with explicit stream synchronization
        # Pinned memory transfer for optimal bandwidth utilization
        with stream:
            result = self.backend.to_numpy(admittances_gpu)

        # Synchronize to ensure transfer completes
        # Critical for correctness - ensures all data is on CPU before return
        stream.synchronize()

        # Clean up GPU arrays explicitly
        del field_gpu, source_gpu, admittances_gpu
        cp.get_default_memory_pool().free_all_blocks()
        stream.synchronize()

        # Return stream to default
        cp.cuda.Stream.null.use()

        return result
