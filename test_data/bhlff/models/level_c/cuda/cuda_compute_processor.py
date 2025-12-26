"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized compute processor for Level C computations.

This module provides CUDA-accelerated block-based processing for Level C
computations with automatic GPU memory management and vectorized operations.

Physical Meaning:
    Provides GPU-accelerated computations for Level C boundary and cell analysis,
    enabling efficient processing of large 7D phase field data with maximum
    performance through CUDA vectorization and optimized block processing.

Mathematical Foundation:
    Implements CUDA-accelerated computations with block-based processing:
    - Block size: optimized for 80% of available GPU memory
    - Vectorized operations: all array operations use GPU kernels
    - Memory-efficient: blocks processed sequentially to fit in GPU memory

Example:
    >>> processor = LevelCCUDAProcessor(bvp_core)
    >>> result = processor.compute_admittance_vectorized(field, source, frequencies)
"""

import numpy as np
from typing import Dict, Any
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from bhlff.core.bvp import BVPCore
from bhlff.utils.cuda_utils import get_cuda_backend_required, CUDABackend
from .cuda_admittance_processor import AdmittanceProcessor
from .cuda_radial_profile_processor import RadialProfileProcessor


class LevelCCUDAProcessor:
    """
    CUDA-optimized compute processor for Level C computations.

    Physical Meaning:
        Provides GPU-accelerated computations for Level C boundary and cell
        analysis with automatic memory management and vectorized operations,
        enabling efficient processing of large 7D phase field data.

    Mathematical Foundation:
        Implements CUDA-accelerated block-based processing:
        - Block size: optimized for 80% of available GPU memory
        - Vectorized operations: all array operations use GPU kernels
        - Memory-efficient: sequential block processing
    """

    def __init__(self, bvp_core: BVPCore, use_cuda: bool = True):
        """
        Initialize CUDA processor for Level C computations.

        Physical Meaning:
            Sets up GPU-accelerated computation system with automatic
            memory management and optimized block processing.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
            use_cuda (bool): Whether to use CUDA acceleration.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.use_cuda = use_cuda and CUDA_AVAILABLE

        # Initialize backend
        # CUDA is required for Level C - no fallback to CPU
        if self.use_cuda:
            try:
                # Use get_cuda_backend_required() to ensure GPU-only execution
                # This raises RuntimeError if CUDA is not available - no CPU fallback
                self.backend = get_cuda_backend_required()
                self.cuda_available = True  # Guaranteed to be CUDA if successful
            except Exception as e:
                self.logger.error(f"CUDA initialization failed: {e}")
                raise RuntimeError(f"Level C requires CUDA: {e}")
        else:
            raise RuntimeError("CUDA not enabled - Level C requires GPU acceleration")

        # Compute optimal block size
        self.block_size = self._compute_optimal_block_size()
        self.logger.info(
            f"Level C CUDA processor initialized: "
            f"CUDA={self.cuda_available}, block_size={self.block_size}"
        )

        # Initialize specialized processors
        self.admittance_processor = AdmittanceProcessor(
            self.backend, self.block_size, self.cuda_available
        )
        self.radial_profile_processor = RadialProfileProcessor(
            self.backend, self.block_size, self.cuda_available
        )

    def _compute_optimal_block_size(self) -> int:
        """
        Compute optimal block size based on GPU memory (80% of available).

        Physical Meaning:
            Calculates block size to use 80% of available GPU memory,
            ensuring efficient memory usage while avoiding OOM errors.

        Returns:
            int: Optimal block size per dimension.
        """
        if not self.cuda_available:
            return 8  # Default CPU block size

        try:
            from ....utils.cuda_utils import calculate_optimal_window_memory

            # For Level C CUDA computations, we need space for:
            # - Input field: 1x
            # - Source field: 1x
            # - Field amplitude squared: 1x (cp.abs(field_gpu) ** 2)
            # - Correlation: 1x (cp.conj(field_gpu) * source_gpu)
            # - Intermediate operations: 2x (temporary arrays)
            # - Reduction buffers: 1x
            # - Output arrays: 1x
            # Total overhead: ~8x for admittance/radial computations
            overhead_factor = 8

            max_window_elements, _, _ = calculate_optimal_window_memory(
                gpu_memory_ratio=0.8,
                overhead_factor=overhead_factor,
                logger=self.logger,
            )

            # For 7D, calculate block size per dimension
            # Assuming roughly equal dimensions
            elements_per_dim = int(max_window_elements ** (1.0 / 7.0))

            # Ensure reasonable bounds (4 to 128)
            block_size = max(4, min(elements_per_dim, 128))

            self.logger.info(f"Optimal block size: {block_size}")

            return block_size

        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size: {e}, using default 8"
            )
            return 8

    def compute_admittance_vectorized(
        self,
        field: np.ndarray,
        source: np.ndarray,
        frequencies: np.ndarray,
        domain: Dict[str, Any],
    ) -> np.ndarray:
        """
        Compute admittance spectrum using vectorized CUDA operations.

        Physical Meaning:
            Computes admittance Y(ω) = I(ω)/V(ω) for all frequencies
            using GPU-accelerated vectorized operations.

        Mathematical Foundation:
            Y(ω) = ∫ a*(x) s(x) dV / ∫ |a(x)|² dV
            Computed for all frequencies simultaneously using vectorization.

        Args:
            field (np.ndarray): Field data.
            source (np.ndarray): Source field.
            frequencies (np.ndarray): Frequencies to compute.
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            np.ndarray: Admittance values for each frequency (complex).
        """
        return self.admittance_processor.compute_vectorized(
            field, source, frequencies, domain
        )

    def compute_radial_profile_vectorized(
        self,
        field: np.ndarray,
        center: np.ndarray,
        radii: np.ndarray,
        domain: Dict[str, Any],
    ) -> np.ndarray:
        """
        Compute radial profile using vectorized CUDA operations.

        Physical Meaning:
            Computes radial profile A(r) = (1/4π) ∫_S(r) |a(x)|² dS
            for all radii using GPU-accelerated vectorized operations.

        Mathematical Foundation:
            A(r) = (1/4π) ∫_S(r) |a(x)|² dS
            Computed for all radii simultaneously using vectorization.

        Args:
            field (np.ndarray): Field data.
            center (np.ndarray): Center point for radial profile.
            radii (np.ndarray): Radii to compute profile.
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            np.ndarray: Radial profile amplitudes for each radius.
        """
        return self.radial_profile_processor.compute_vectorized(
            field, center, radii, domain
        )

    def cleanup(self) -> None:
        """Clean up GPU memory."""
        if self.cuda_available and isinstance(self.backend, CUDABackend):
            try:
                cp.get_default_memory_pool().free_all_blocks()
                cp.get_default_pinned_memory_pool().free_all_blocks()
            except Exception as e:
                self.logger.warning(f"GPU memory cleanup failed: {e}")
