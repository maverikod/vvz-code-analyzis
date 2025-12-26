"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Lazy 7D field with block-based access.

This module provides transparent lazy access to large 7D fields through
block-based processing, where only the current block is in memory.

Physical Meaning:
    Represents a 7D phase field that is generated on-demand in blocks,
    with only the current block in memory and other blocks stored on disk.
    Enables efficient access to large 7D fields that exceed available memory.

Mathematical Foundation:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Field is decomposed into blocks of manageable size
    - Blocks are accessed transparently through slicing
    - Only current block is in memory

Example:
    >>> generator = BlockedFieldGenerator(domain, source_generator)
    >>> field = generator.get_field()  # Returns BlockedField
    >>> block = field[0:8, 0:8, 0:8, 0:4, 0:4, 0:4, 0:8]  # Accesses block
"""

import numpy as np
from typing import Dict, Any, Iterator, TYPE_CHECKING

from ..domain import Domain

if TYPE_CHECKING:
    from .blocked_field_generator import BlockedFieldGenerator


class BlockedField:
    """
    Lazy 7D field with block-based access.

    Physical Meaning:
        Represents a 7D phase field that is generated on-demand in blocks,
        with only the current block in memory and other blocks stored on disk.
        Provides transparent access to any block of the 7D field through
        slicing operations, preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Field shape: (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)
        - Block access: transparent slicing over 7 dimensions
        - Memory efficient: only current block in memory

    Attributes:
        domain (Domain): Computational domain.
        generator (BlockedFieldGenerator): Block generator instance.
        shape (Tuple[int, ...]): Field shape (7-tuple).
        dtype (type): Data type of the field (default: complex).
    """

    def __init__(
        self,
        domain: Domain,
        generator: "BlockedFieldGenerator",
        dtype: type = complex,
    ) -> None:
        """
        Initialize blocked field.

        Physical Meaning:
            Sets up lazy field access with block-based processing for
            efficient memory management of large 7D phase fields.

        Args:
            domain (Domain): Computational domain.
            generator (BlockedFieldGenerator): Block generator instance.
            dtype (type): Data type of the field (default: complex).
        """
        self.domain = domain
        self.generator = generator
        self.shape = domain.shape
        self.dtype = dtype

    @property
    def ndim(self) -> int:
        """
        Number of dimensions of the field.

        Returns:
            int: Number of dimensions (always 7 for 7D space-time).
        """
        return len(self.shape)

    def __getitem__(self, key) -> np.ndarray:
        """
        Access field block using slicing.

        Physical Meaning:
            Provides transparent access to any block of the 7D field,
            automatically generating and caching blocks as needed.
            Preserves 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Args:
            key: Slice or tuple of slices for 7D indexing.

        Returns:
            np.ndarray: Requested field block (7D array).
        """
        return self.generator.get_block(key)

    def get_block(self, block_indices: tuple) -> np.ndarray:
        """
        Get specific block by indices.

        Physical Meaning:
            Retrieves the specified 7D block by its block indices,
            preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Args:
            block_indices (tuple): Block indices in each dimension (7-tuple).

        Returns:
            np.ndarray: Field block (7D array).
        """
        return self.generator.get_block_by_indices(block_indices)

    def iterate_blocks(
        self,
    ) -> Iterator[tuple[np.ndarray, Dict[str, Any]]]:
        """
        Iterate over all blocks in the field.

        Physical Meaning:
            Iterates over all blocks of the 7D field, providing access
            to each block with its metadata for batch processing.

        Yields:
            Tuple[np.ndarray, Dict[str, Any]]: Block data and metadata.
        """
        return self.generator.iterate_blocks()
