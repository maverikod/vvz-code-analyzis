"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block metadata for field block caching.

This module provides metadata structures for tracking block information
in the blocked field generator system.

Physical Meaning:
    Metadata stores essential information about cached field blocks,
    enabling efficient validation and management of block cache integrity
    for 7D phase field computations.

Mathematical Foundation:
    Block metadata contains:
    - Block indices: (i_x, i_y, i_z, i_φ₁, i_φ₂, i_φ₃, i_t)
    - Block shape: (B_x, B_y, B_z, B_φ₁, B_φ₂, B_φ₃, B_t)
    - Cache status and file paths

Example:
    >>> metadata = BlockMetadata(
    ...     block_id="abc123",
    ...     block_indices=(0, 0, 0, 0, 0, 0, 0),
    ...     block_shape=(8, 8, 8, 4, 4, 4, 8),
    ...     file_path="/cache/block_abc123.npy",
    ...     is_generated=True,
    ...     is_cached=True
    ... )
"""

from typing import Tuple
from dataclasses import dataclass


@dataclass
class BlockMetadata:
    """
    Metadata for a field block.

    Physical Meaning:
        Stores metadata information about a cached field block, including
        its position, shape, and cache status for 7D phase field blocks.

    Attributes:
        block_id (int): Unique identifier for the block.
        block_indices (Tuple[int, ...]): Block indices in each dimension (7-tuple).
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            (i_x, i_y, i_z, i_φ₁, i_φ₂, i_φ₃, i_t)
        block_shape (Tuple[int, ...]): Block shape in each dimension (7-tuple).
            For 7D space-time: (B_x, B_y, B_z, B_φ₁, B_φ₂, B_φ₃, B_t)
        file_path (str): Path to the cached block file.
        is_generated (bool): Whether the block has been generated.
        is_cached (bool): Whether the block is cached on disk.
    """

    block_id: int
    block_indices: Tuple[int, ...]
    block_shape: Tuple[int, ...]
    file_path: str
    is_generated: bool
    is_cached: bool
