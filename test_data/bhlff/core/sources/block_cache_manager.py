"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block cache manager for field block caching and validation.

This module provides cache management functionality for block-based field
generation, including loading, saving, and metadata validation for 7D blocks.

Physical Meaning:
    Manages disk-based caching of 7D field blocks with metadata validation,
    ensuring cache integrity and efficient block access for large 7D phase
    fields that exceed available memory.

Mathematical Foundation:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Blocks are cached on disk using np.save/np.load
    - Metadata validates block_shape matches actual block shape
    - Vectorized shape comparison ensures 7D structure integrity

Example:
    >>> cache_manager = BlockCacheManager(cache_dir, logger)
    >>> block_id = cache_manager.get_block_id(block_indices)
    >>> block_path = cache_manager.get_block_path(block_id)
    >>> block = cache_manager.load_block(block_path, block_indices)
"""

import numpy as np
import pickle
import hashlib
import logging
from typing import Tuple, Optional, Dict
from pathlib import Path

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .block_metadata import BlockMetadata


class BlockCacheManager:
    """
    Block cache manager for disk-based caching with metadata validation.

    Physical Meaning:
        Manages caching of 7D field blocks on disk with metadata validation,
        ensuring cache integrity and efficient block access. Validates that
        metadata block_shape matches actual loaded block shape for 7D structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Block caching: np.save/np.load (not raw tofile)
        - Metadata validation: vectorized shape comparison
        - Cache integrity: ensures block_shape matches actual shape

    Attributes:
        cache_dir (Path): Cache directory path.
        logger: Logger instance.
    """

    def __init__(self, cache_dir: Path, logger: logging.Logger) -> None:
        """
        Initialize block cache manager.

        Args:
            cache_dir (Path): Cache directory path.
            logger (logging.Logger): Logger instance.
        """
        self.cache_dir = cache_dir
        self.logger = logger

    def get_block_id(self, block_indices: Tuple[int, ...]) -> str:
        """
        Generate unique block ID from indices.

        Physical Meaning:
            Creates a unique identifier for a block based on its position
            in the 7D block grid, enabling efficient cache lookup.

        Args:
            block_indices (Tuple[int, ...]): Block indices (7-tuple).

        Returns:
            str: Unique block identifier (MD5 hash).
        """
        indices_str = "_".join(str(i) for i in block_indices)
        return hashlib.md5(indices_str.encode()).hexdigest()

    def get_block_path(self, block_id: str) -> Path:
        """
        Get file path for block cache.

        Args:
            block_id (str): Block identifier.

        Returns:
            Path: Path to cached block file.
        """
        return self.cache_dir / f"block_{block_id}.npy"

    def get_metadata_path(self, block_id: str) -> Path:
        """
        Get file path for block metadata.

        Args:
            block_id (str): Block identifier.

        Returns:
            Path: Path to metadata file.
        """
        return self.cache_dir / f"block_{block_id}.meta"

    def load_block(
        self,
        block_path: Path,
        block_indices: Tuple[int, ...],
    ) -> Optional[np.ndarray]:
        """
        Load block from cache with validation.

        Physical Meaning:
            Loads a 7D block from disk cache with validation of dimensionality
            and structure, ensuring the block preserves 7D structure
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Args:
            block_path (Path): Path to cached block file.
            block_indices (Tuple[int, ...]): Block indices (7-tuple).

        Returns:
            Optional[np.ndarray]: Loaded block or None if loading failed.
        """
        if not block_path.exists():
            return None

        self.logger.debug(f"Loading block {block_indices} from cache")

        # Load block using np.load (not raw tofile) - preserves array structure
        try:
            block = np.load(block_path, mmap_mode=None)  # Load fully into memory
        except Exception as e:
            self.logger.warning(
                f"Failed to load block {block_indices} from cache: {e}. "
                f"Regenerating block."
            )
            return None

        # Validate 7D structure
        if block is not None and block.ndim != 7:
            self.logger.warning(
                f"Cached block has wrong dimensionality: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {block.ndim}D. "
                f"Regenerating block."
            )
            return None

        return block

    def validate_metadata(
        self,
        metadata_path: Path,
        block: np.ndarray,
        block_indices: Tuple[int, ...],
    ) -> Tuple[bool, Optional[BlockMetadata]]:
        """
        Validate metadata matches actual block shape.

        Physical Meaning:
            Validates that cached metadata block_shape matches the actual
            loaded block shape, ensuring cache integrity for 7D structure.
            Uses vectorized comparison for efficiency.

        Args:
            metadata_path (Path): Path to metadata file.
            block (np.ndarray): Loaded block (7D array).
            block_indices (Tuple[int, ...]): Block indices (7-tuple).

        Returns:
            Tuple[bool, Optional[BlockMetadata]]: (is_valid, metadata).
        """
        if not metadata_path.exists():
            return False, None

        try:
            with open(metadata_path, "rb") as f:
                metadata = pickle.load(f)

            # Ensure metadata block_shape matches actual block shape
            if hasattr(metadata, "block_shape"):
                # Vectorized shape comparison (7D)
                if isinstance(metadata.block_shape, tuple):
                    shape_array = np.array(metadata.block_shape, dtype=np.int64)
                    actual_shape_array = np.array(block.shape, dtype=np.int64)
                    # Vectorized comparison
                    if shape_array.shape == actual_shape_array.shape:
                        shape_match = np.array_equal(shape_array, actual_shape_array)
                    else:
                        shape_match = False
                else:
                    shape_match = metadata.block_shape == block.shape

                if not shape_match:
                    self.logger.warning(
                        f"Metadata block_shape mismatch for block "
                        f"{block_indices}: "
                        f"metadata={metadata.block_shape}, "
                        f"actual={block.shape}. "
                        f"Updating metadata to match true block shape."
                    )
                    return False, metadata
                else:
                    # Validate metadata has 7D structure
                    if len(metadata.block_shape) != 7:
                        self.logger.warning(
                            f"Metadata block_shape has wrong dimensionality: "
                            f"expected 7D, got {len(metadata.block_shape)}D. "
                            f"Updating metadata."
                        )
                        return False, metadata
                    return True, metadata
        except Exception as e:
            self.logger.warning(
                f"Failed to load/validate metadata for block "
                f"{block_indices}: {e}. Regenerating metadata."
            )
            return False, None

        return False, None

    def save_block(
        self,
        block_path: Path,
        block: np.ndarray,
    ) -> None:
        """
        Save block to disk cache.

        Physical Meaning:
            Saves a 7D block to disk using np.save (not raw tofile),
            preserving array structure and ensuring efficient storage.

        Args:
            block_path (Path): Path to save block file.
            block (np.ndarray): Block to save (7D array).
        """
        # Save to disk using np.save (not raw tofile) - preserves array structure
        # Use vectorized save operation
        np.save(block_path, block, allow_pickle=False)

    def save_block_metadata(
        self,
        block_id: str,
        block_indices: Tuple[int, ...],
        block_shape: Tuple[int, ...],
        file_path: Path,
        block_metadata: Optional[Dict[str, BlockMetadata]] = None,
    ) -> None:
        """
        Save block metadata.

        Physical Meaning:
            Saves metadata for a cached block, including block indices,
            shape, and cache status for 7D structure validation.

        Args:
            block_id (str): Block identifier.
            block_indices (Tuple[int, ...]): Block indices (7-tuple).
            block_shape (Tuple[int, ...]): Block shape (7-tuple).
            file_path (Path): Path to cached block file.
            block_metadata (Optional[Dict[str, BlockMetadata]]): Metadata cache
                dictionary to update (optional).
        """
        metadata = BlockMetadata(
            block_id=block_id,
            block_indices=block_indices,
            block_shape=block_shape,
            file_path=str(file_path),
            is_generated=True,
            is_cached=True,
        )
        metadata_path = self.get_metadata_path(block_id)
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f)
        if block_metadata is not None:
            block_metadata[block_id] = metadata
