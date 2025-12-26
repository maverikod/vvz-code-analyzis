"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized blocked field processor for memory evolution.

This module implements block processing for 7D blocked fields with
CUDA acceleration and proper 7D structure preservation.

Physical Meaning:
    Processes 7D blocked field blocks using generator with max_blocks limit,
    extracting 3D spatial field by averaging over phase and temporal dimensions.
    Uses vectorized operations with CUDA acceleration. Fixes broadcasting issues
    by properly computing spatial indices from 7D block metadata.

Theoretical Background:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Block iteration: uses generator.iterate_blocks(max_blocks) for memory safety
    - 3D extraction: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
    - Spatial indices: computed from first 3 dimensions of 7D block_indices and block_size
    - Broadcasting fix: ensures block_spatial shape matches expected size
    - CUDA optimization: uses 80% GPU memory limit with vectorized operations

Example:
    >>> processor = BlockedFieldProcessorCUDA(spatial_extractor)
    >>> field = processor.process_blocked_field_blocks(blocked_field, generator, N, cuda_available)
"""

import numpy as np
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class BlockedFieldProcessorCUDA:
    """
    CUDA-optimized blocked field processor.

    Physical Meaning:
        Processes 7D blocked field blocks using generator with max_blocks limit,
        extracting 3D spatial field by averaging over phase and temporal dimensions.
        Uses vectorized operations with CUDA acceleration.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Block iteration: uses generator.iterate_blocks(max_blocks) for memory safety
        - 3D extraction: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
        - Spatial indices: computed from first 3 dimensions of 7D block_indices and block_size
        - Broadcasting fix: ensures block_spatial shape matches expected size
    """

    def __init__(self, spatial_extractor: Any):
        """
        Initialize blocked field processor.

        Args:
            spatial_extractor: Spatial field extractor instance.
        """
        self.spatial_extractor = spatial_extractor
        self.logger = logging.getLogger(__name__)

    def process_blocked_field_blocks(
        self,
        blocked_field: Any,
        generator: Any,
        N: int,
        cuda_available: bool,
    ) -> np.ndarray:
        """
        Process blocked field blocks and extract 3D spatial field.

        Physical Meaning:
            Processes 7D blocked field blocks using generator with max_blocks limit,
            extracting 3D spatial field by averaging over phase and temporal dimensions.
            Uses vectorized operations with CUDA acceleration.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Block iteration: uses generator.iterate_blocks(max_blocks) for memory safety
            - 3D extraction: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
            - Spatial indices: computed from first 3 dimensions of 7D block_indices and block_size
            - Broadcasting fix: ensures block_spatial shape matches expected size

        Args:
            blocked_field (Any): BlockedField instance.
            generator (Any): BlockedFieldGenerator instance.
            N (int): Domain size (N×N×N).
            cuda_available (bool): Whether CUDA is available.

        Returns:
            np.ndarray: 3D spatial field (N, N, N).
        """
        field = np.zeros((N, N, N), dtype=np.complex128)

        # Calculate max_blocks based on memory constraints (80% GPU limit)
        max_blocks = self.spatial_extractor.calculate_max_blocks(
            generator, cuda_available
        )

        # Iterate through blocks using generator with max_blocks limit
        for block_data, block_meta in generator.iterate_blocks(max_blocks=max_blocks):
            # Validate and extract spatial part
            if not self._validate_and_extract_block(
                block_data, block_meta, generator, field, N, cuda_available
            ):
                continue

        return field

    def _validate_and_extract_block(
        self,
        block_data: np.ndarray,
        block_meta: Dict[str, Any],
        generator: Any,
        field: np.ndarray,
        N: int,
        cuda_available: bool,
    ) -> bool:
        """
        Validate block and extract spatial part into 3D field.

        Physical Meaning:
            Validates 7D block structure, extracts 3D spatial part by averaging
            over phase/temporal dimensions, and assigns to correct position in 3D field.
            Fixes broadcasting issues by proper size matching.

        Args:
            block_data (np.ndarray): 7D block data.
            block_meta (Dict[str, Any]): Block metadata.
            generator (Any): BlockedFieldGenerator instance.
            field (np.ndarray): 3D output field to update.
            N (int): Domain size.
            cuda_available (bool): Whether CUDA is available.

        Returns:
            bool: True if block was successfully processed, False otherwise.
        """
        # Validate 7D block structure
        if block_data.ndim != 7:
            self.logger.warning(
                f"Skipping block {block_meta.get('block_indices', 'unknown')}: "
                f"expected 7D, got {block_data.ndim}D"
            )
            return False

        # Extract 3D spatial part by averaging over phase/temporal dimensions (3,4,5,6)
        block_spatial = self.spatial_extractor.extract_spatial_from_7d_block(
            block_data, cuda_available
        )

        # Validate extracted spatial block has 3D structure
        if block_spatial.ndim != 3:
            self.logger.warning(
                f"Skipping block {block_meta.get('block_indices', 'unknown')}: "
                f"extracted spatial block has {block_spatial.ndim}D, expected 3D"
            )
            return False

        # Extract spatial indices from block metadata
        block_indices = block_meta["block_indices"]
        block_shape_7d = block_meta["block_shape"]

        # Validate block_indices has 7 elements
        if len(block_indices) != 7:
            self.logger.warning(
                f"Skipping block: block_indices has {len(block_indices)} "
                f"elements, expected 7 for 7D space-time M₇"
            )
            return False

        # Validate block_size
        block_size_7d = generator.block_size
        if len(block_size_7d) != 7:
            self.logger.warning(
                f"Invalid block_size: expected 7D, got {len(block_size_7d)}D"
            )
            return False

        # Calculate spatial block position in 3D field
        i_start = block_indices[0] * block_size_7d[0]
        j_start = block_indices[1] * block_size_7d[1]
        k_start = block_indices[2] * block_size_7d[2]

        # Spatial block size from first 3 dimensions
        spatial_block_shape = block_shape_7d[:3]
        i_size = min(spatial_block_shape[0], block_spatial.shape[0])
        j_size = min(spatial_block_shape[1], block_spatial.shape[1])
        k_size = min(spatial_block_shape[2], block_spatial.shape[2])

        # Calculate end indices respecting domain boundaries
        i_end = min(i_start + i_size, N)
        j_end = min(j_start + j_size, N)
        k_end = min(k_start + k_size, N)

        # Adjust actual sizes to fit within domain
        actual_i_size = i_end - i_start
        actual_j_size = j_end - j_start
        actual_k_size = k_end - k_start

        # Ensure block_spatial matches expected size (fixes broadcasting issues)
        if (
            block_spatial.shape[0] >= actual_i_size
            and block_spatial.shape[1] >= actual_j_size
            and block_spatial.shape[2] >= actual_k_size
        ):
            # Use vectorized assignment with proper slicing
            field[i_start:i_end, j_start:j_end, k_start:k_end] = (
                block_spatial[:actual_i_size, :actual_j_size, :actual_k_size]
            )
            return True
        else:
            self.logger.warning(
                f"Block spatial size mismatch: "
                f"expected ({actual_i_size}, {actual_j_size}, {actual_k_size}), "
                f"got {block_spatial.shape}"
            )
            return False

