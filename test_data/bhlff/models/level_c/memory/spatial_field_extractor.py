"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spatial field extractor for 7D-to-3D conversion with CUDA support.

This module implements extraction of 3D spatial fields from 7D BlockedField
by averaging over phase and temporal dimensions using vectorized operations
with CUDA acceleration. Preserves 7D-to-3D semantics with proper broadcasting.

Physical Meaning:
    Extracts 3D spatial field from 7D phase field M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    by averaging over phase and temporal dimensions. Uses block-based processing
    with CUDA acceleration respecting 80% GPU memory limit.

Mathematical Foundation:
    For 7D field a(x, y, z, φ₁, φ₂, φ₃, t):
    a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
    where ⟨·⟩ denotes averaging over phase and temporal dimensions.

Example:
    >>> extractor = SpatialFieldExtractor()
    >>> field_3d = extractor.extract_spatial_from_7d_block(block_7d, use_cuda=True)
"""

import numpy as np
from typing import Any, Optional
import logging

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class SpatialFieldExtractor:
    """
    Extractor for 3D spatial fields from 7D blocks with CUDA support.

    Physical Meaning:
        Extracts 3D spatial field from 7D block by averaging over phase
        and temporal dimensions (indices 3,4,5,6). Uses vectorized operations
        with CUDA acceleration when available. Preserves 7D-to-3D semantics.

    Mathematical Foundation:
        For 7D block a(x, y, z, φ₁, φ₂, φ₃, t):
        a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
        where ⟨·⟩ denotes averaging over phase and temporal dimensions.
    """

    def __init__(self):
        """Initialize spatial field extractor."""
        self.logger = logging.getLogger(__name__)

    def extract_spatial_from_7d_block(
        self, block_data: np.ndarray, use_cuda: bool
    ) -> np.ndarray:
        """
        Extract 3D spatial field from 7D block by averaging over phase/time dimensions.

        Physical Meaning:
            Extracts 3D spatial field from 7D block by averaging over phase
            and temporal dimensions (indices 3,4,5,6). Uses vectorized operations
            with CUDA acceleration when available. Preserves 7D-to-3D semantics.

        Mathematical Foundation:
            For 7D block a(x, y, z, φ₁, φ₂, φ₃, t):
            a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
            where ⟨·⟩ denotes averaging over phase and temporal dimensions.

        Args:
            block_data (np.ndarray): 7D block data with shape
                (N_x, N_y, N_z, N_phi, N_phi, N_phi, N_t).
            use_cuda (bool): Whether to use CUDA for computation.

        Returns:
            np.ndarray: 3D spatial field with shape (N_x, N_y, N_z).

        Raises:
            ValueError: If block_data is not 7D.
        """
        # Validate 7D structure
        if block_data.ndim != 7:
            raise ValueError(
                f"Expected 7D block for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {block_data.ndim}D block with shape {block_data.shape}"
            )

        if use_cuda and CUDA_AVAILABLE:
            try:
                return self._extract_spatial_cuda(block_data)
            except Exception as e:
                self.logger.debug(f"CUDA extraction failed: {e}. Using CPU fallback.")
                return self._extract_spatial_cpu(block_data)
        else:
            return self._extract_spatial_cpu(block_data)

    def _extract_spatial_cuda(self, block_data: np.ndarray) -> np.ndarray:
        """
        Extract 3D spatial field using CUDA with 80% GPU memory limit.

        Physical Meaning:
            Extracts 3D spatial field on GPU using vectorized operations
            with 80% GPU memory limit. Falls back to CPU if memory insufficient.

        Args:
            block_data (np.ndarray): 7D block data.

        Returns:
            np.ndarray: 3D spatial field.
        """
        # Transfer to GPU if needed
        if isinstance(block_data, np.ndarray):
            block_gpu = cp.asarray(block_data)
        else:
            block_gpu = block_data

        # Check GPU memory limit (80%)
        block_memory = block_gpu.nbytes
        mem_info = cp.cuda.runtime.memGetInfo()
        free_memory_bytes = mem_info[0]
        available_memory_bytes = int(free_memory_bytes * 0.8)  # 80% limit

        # Overhead factor for mean computation
        overhead_factor = 2.0  # original + result
        required_memory = block_memory * overhead_factor

        if required_memory <= available_memory_bytes:
            # Use CUDA vectorized mean over phase and temporal dimensions (indices 3,4,5,6)
            # Physical meaning: average amplitude over phase and time
            block_spatial_gpu = cp.mean(cp.abs(block_gpu), axis=(3, 4, 5, 6))
            # Convert back to CPU
            block_spatial = cp.asnumpy(block_spatial_gpu)
            # Cleanup GPU memory
            del block_gpu, block_spatial_gpu
            cp.get_default_memory_pool().free_all_blocks()
            return block_spatial
        else:
            # Fallback to CPU if GPU memory insufficient
            self.logger.warning(
                f"Block size {block_memory/1e6:.2f}MB exceeds "
                f"80% GPU memory limit ({available_memory_bytes/1e6:.2f}MB). "
                f"Using CPU computation."
            )
            # Use NumPy vectorized mean over phase and temporal dimensions
            return np.mean(np.abs(block_data), axis=(3, 4, 5, 6))

    def _extract_spatial_cpu(self, block_data: np.ndarray) -> np.ndarray:
        """
        Extract 3D spatial field using CPU with vectorized operations.

        Physical Meaning:
            Extracts 3D spatial field on CPU using NumPy vectorized operations.

        Args:
            block_data (np.ndarray): 7D block data.

        Returns:
            np.ndarray: 3D spatial field.
        """
        # Use NumPy vectorized mean over phase and temporal dimensions
        return np.mean(np.abs(block_data), axis=(3, 4, 5, 6))

    def calculate_max_blocks(
        self, generator: Any, cuda_available: bool
    ) -> int:
        """
        Calculate maximum number of blocks to process based on memory constraints.

        Physical Meaning:
            Calculates safe maximum number of blocks to process based on
            available memory (80% GPU limit if CUDA available, otherwise CPU memory).

        Mathematical Foundation:
            max_blocks = min(default_limit, available_memory / (block_memory * overhead))

        Args:
            generator (Any): BlockedFieldGenerator instance.
            cuda_available (bool): Whether CUDA is available.

        Returns:
            int: Maximum number of blocks to process.
        """
        # Default safety limit
        default_max_blocks = 10000

        if cuda_available and CUDA_AVAILABLE:
            try:
                from ....utils.cuda_utils import calculate_optimal_window_memory

                # Calculate based on GPU memory (80% limit)
                block_volume = np.prod(generator.block_size)
                bytes_per_element = 16  # complex128
                block_memory = block_volume * bytes_per_element

                # Overhead factor for block processing
                overhead_factor = 3.0  # original + spatial + result
                
                # Get optimal window memory based on TOTAL GPU memory
                max_window_elements, _, _ = calculate_optimal_window_memory(
                    gpu_memory_ratio=0.8,
                    overhead_factor=overhead_factor,
                    logger=self.logger,
                )
                
                max_window_memory = max_window_elements * bytes_per_element
                max_blocks_by_memory = int(
                    max_window_memory / (block_memory * overhead_factor)
                )

                # Use minimum of default and memory-based limit
                max_blocks = min(default_max_blocks, max_blocks_by_memory)
            except Exception as e:
                self.logger.debug(
                    f"Could not calculate GPU-based max_blocks: {e}. "
                    f"Using default limit."
                )
                max_blocks = default_max_blocks
        else:
            # CPU-based calculation (simplified)
            max_blocks = default_max_blocks

        return max_blocks






