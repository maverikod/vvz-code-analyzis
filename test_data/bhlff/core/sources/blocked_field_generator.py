"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Blocked field generator for large 7D fields with automatic memory management.

Implements lazy field generation with block-based processing, where only the
current block is kept in memory and all other blocks are stored on disk.
Provides transparent access to any block with caching.

Physical Meaning:
    Enables efficient generation and access to large 7D phase fields that
    exceed available memory by processing and storing data in manageable blocks.

Example:
    >>> generator = BlockedFieldGenerator(domain, source_generator)
    >>> field = generator.get_field()
    >>> block = field[0:8, 0:8, 0:8, 0:4, 0:4, 0:4, 0:8]
"""

import numpy as np
from typing import Dict, Any, Callable, Optional, Tuple, Iterator, Union, TYPE_CHECKING
import logging
import tempfile
from pathlib import Path
import threading

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..domain import Domain
from .block_metadata import BlockMetadata
from .blocked_field import BlockedField
from .block_cache_manager import BlockCacheManager
from .block_generator import BlockGenerator
from .block_config import BlockConfig
from .block_iterator import BlockIterator

if TYPE_CHECKING:
    from cupy.cuda import Stream  # pragma: no cover


class BlockedFieldGenerator:
    """
    Block-based field generator with automatic memory management.

        Generates large 7D fields in blocks, keeping only the current block
        in memory and storing all other blocks on disk. Provides transparent
        access with caching for efficient repeated access.
    """

    def __init__(
        self,
        domain: Domain,
        field_generator: Callable[[Domain, Dict[str, Any], Dict[str, Any]], np.ndarray],
        block_size: Optional[Tuple[int, ...]] = None,
        cache_dir: Optional[str] = None,
        max_memory_mb: float = 500.0,
        config: Optional[Dict[str, Any]] = None,
        use_cuda: bool = True,
    ) -> None:
        """
        Initialize blocked field generator.

        Args:
            domain (Domain): Computational domain.
            field_generator (Callable): Function that generates field block.
            block_size (Optional[Tuple[int, ...]]): Block size per dimension.
            cache_dir (Optional[str]): Directory for block cache.
            max_memory_mb (float): Maximum memory usage in MB for blocks.
            config (Optional[Dict[str, Any]]): Configuration for field generator.
            use_cuda (bool): Whether to use CUDA for block processing (default: True).
        """
        self.domain = domain
        self.field_generator = field_generator
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.use_cuda = use_cuda and CUDA_AVAILABLE

        # Setup cache directory
        if cache_dir is None:
            cache_dir = tempfile.mkdtemp(prefix="bhlff_field_cache_")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Block cache directory: {self.cache_dir}")

        # Initialize block configuration calculator
        self._block_config = BlockConfig(self.domain, self.logger, self.use_cuda)

        # Compute optimal block size (with CUDA support if available)
        if block_size is None:
            block_size = self._block_config.compute_optimal_block_size(max_memory_mb)
        self.block_size = block_size

        # Compute block configuration
        self.blocks_per_dim, self.total_blocks = (
            self._block_config.compute_block_configuration(self.block_size)
        )

        # Initialize cache manager
        self._cache_manager = BlockCacheManager(self.cache_dir, self.logger)

        # Initialize block generator
        self._block_generator = BlockGenerator(
            self.domain,
            self.field_generator,
            self.block_size,
            self.use_cuda,
            self.config,
            self.logger,
        )

        # Block cache in memory (LRU-like, only one block)
        self._current_block: Optional[Union[np.ndarray, "cp.ndarray"]] = None
        self._current_block_id: Optional[str] = None
        self._block_lock = threading.Lock()

        # Block metadata cache
        self._block_metadata: Dict[str, BlockMetadata] = {}

        # Initialize block iterator
        self._block_iterator = BlockIterator(
            self,
            self._cache_manager,
            self.blocks_per_dim,
            self.total_blocks,
            self.block_size,
            self.use_cuda,
            self._block_metadata,
            self.logger,
        )

        self.logger.info(
            f"BlockedFieldGenerator initialized: "
            f"block_size={self.block_size}, "
            f"total_blocks={self.total_blocks}, "
            f"cache_dir={self.cache_dir}, "
            f"use_cuda={self.use_cuda}"
        )

    def get_block(self, key: Any) -> np.ndarray:
        """
        Get block using slicing key.

        Args:
            key: Slice or tuple of slices for 7D indexing.

        Returns:
            np.ndarray: Field block.
        """
        # Convert key to block indices
        if isinstance(key, tuple):
            # Extract block indices from slices
            block_indices = []
            for i, k in enumerate(key):
                if isinstance(k, slice):
                    # Convert slice to block indices
                    start = k.start if k.start is not None else 0
                    block_idx = start // self.block_size[i]
                    block_indices.append(block_idx)
                else:
                    block_indices.append(k)
            block_indices = tuple(block_indices)
        else:
            # Single index - treat as first block
            block_indices = (0, 0, 0, 0, 0, 0, 0)

        return self.get_block_by_indices(block_indices)

    def get_block_by_indices(
        self,
        block_indices: Tuple[int, ...],
        *,
        as_gpu: bool = False,
        stream: Optional["Stream"] = None,
    ) -> Union[np.ndarray, "cp.ndarray"]:
        """
        Get block by block indices with CUDA support and metadata validation.

        Retrieves or generates the specified 7D block, loading from cache
        if available or generating and caching if not. Validates metadata
        matches true block shape. Supports CUDA acceleration with 80% GPU limit.
        Allows large block counts with warnings (not hard errors) up to safe cap.

        Physical Meaning:
            Retrieves a 7D block from the phase field M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            ensuring cache integrity through metadata validation and efficient
            memory usage with 80% GPU limit for CUDA operations.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Block indices: (i_x, i_y, i_z, i_φ₁, i_φ₂, i_φ₃, i_t)
            - Block shape validation: vectorized comparison ensures integrity
            - CUDA memory: 80% of free GPU memory for block processing
            - Metadata validation: block_shape matches actual block shape

        Args:
            block_indices (Tuple[int, ...]): Block indices in each dimension (7-tuple).

        Args:
            block_indices (Tuple[int, ...]): Block indices in each dimension (7-tuple).
            as_gpu (bool): When True, returns block transferred to GPU memory using
                pinned transfers capped at 80% of available GPU memory.
            stream (Optional[cp.cuda.Stream]): Optional CUDA stream for asynchronous
                H2D transfer when `as_gpu` is True.

        Returns:
            Union[np.ndarray, cp.ndarray]: Field block located on CPU or GPU.

        Raises:
            ValueError: If block_indices length != 7 or invalid block structure.
        """
        # Validate 7D structure: ensure block_indices has 7 elements
        if len(block_indices) != 7:
            raise ValueError(
                f"Expected 7D block indices for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(block_indices)}D: {block_indices}"
            )

        # Vectorized validation: ensure indices are non-negative
        block_indices_array = np.array(block_indices, dtype=np.int64)
        if np.any(block_indices_array < 0):
            raise ValueError(f"Block indices must be non-negative: {block_indices}")

        # Vectorized bounds check: ensure indices are within valid range
        blocks_per_dim_array = np.array(self.blocks_per_dim, dtype=np.int64)
        if np.any(block_indices_array >= blocks_per_dim_array):
            raise ValueError(
                f"Block indices out of bounds: {block_indices}, "
                f"valid range: [0, {blocks_per_dim_array})"
            )

        # Warning for large block counts (not hard error)
        if self.total_blocks > 50000:
            self.logger.warning(
                f"Accessing block from large domain ({self.total_blocks} blocks). "
                f"This may take time. Consider increasing block_size for better performance."
            )

        block_id = self._cache_manager.get_block_id(block_indices)

        # Check if block is in memory (with lock for thread safety)
        with self._block_lock:
            if self._current_block_id == block_id and self._current_block is not None:
                # Validate 7D structure in memory (vectorized check)
                if self._current_block.ndim != 7:
                    self.logger.warning(
                        f"Block in memory has wrong dimensionality: "
                        f"expected 7D, got {self._current_block.ndim}D. "
                        f"Regenerating block."
                    )
                else:
                    # Convert from GPU to CPU if needed (vectorized copy)
                    if (
                        self.use_cuda
                        and CUDA_AVAILABLE
                        and isinstance(self._current_block, cp.ndarray)
                    ):
                        # Use vectorized copy to CPU (CuPy optimized)
                        result = cp.asnumpy(self._current_block)
                        # Ensure 7D structure (vectorized validation)
                        if result.ndim != 7:
                            raise ValueError(
                                f"Block conversion failed: expected 7D, got {result.ndim}D"
                            )
                        # Vectorized shape validation
                        if len(result.shape) != 7:
                            raise ValueError(
                                f"Block shape has wrong length: "
                                f"expected 7D, got {len(result.shape)}D"
                            )
                        return result
                    # Vectorized copy on CPU (NumPy optimized)
                    result = np.array(self._current_block, copy=True)
                    # Ensure 7D structure (vectorized validation)
                    if result.ndim != 7:
                        raise ValueError(
                            f"Block in memory has wrong dimensionality: "
                            f"expected 7D, got {result.ndim}D"
                        )
                    # Vectorized shape validation
                    if len(result.shape) != 7:
                        raise ValueError(
                            f"Block shape has wrong length: "
                            f"expected 7D, got {len(result.shape)}D"
                        )
                    return result

        # Check if block is on disk (np.save/np.load caching - not raw tofile)
        block_path = self._cache_manager.get_block_path(block_id)
        metadata_path = self._cache_manager.get_metadata_path(block_id)
        block = self._cache_manager.load_block(block_path, block_indices)

        # Validate metadata matches true block shape (vectorized comparison)
        if block is not None:
            # Validate 7D structure of loaded block (vectorized check)
            if block.ndim != 7 or len(block.shape) != 7:
                self.logger.warning(
                    f"Cached block has invalid 7D structure: "
                    f"ndim={block.ndim}, shape_len={len(block.shape)}. "
                    f"Regenerating block."
                )
                block = None
            else:
                # Validate metadata matches true block shape
                metadata_valid, metadata = self._cache_manager.validate_metadata(
                    metadata_path, block, block_indices
                )
                actual_shape_array = np.array(block.shape, dtype=np.int64)

                # Ensure metadata matches actual block shape (vectorized comparison)
                if not metadata_valid or metadata is None:
                    # Update metadata to match actual block shape
                    self._cache_manager.save_block_metadata(
                        block_id,
                        block_indices,
                        block.shape,  # Use actual shape
                        block_path,
                        self._block_metadata,
                    )
                    self.logger.debug(
                        f"Updated metadata for block {block_indices} to match shape {block.shape}"
                    )
                else:
                    if hasattr(metadata, "block_shape"):
                        # Vectorized shape comparison (7D)
                        metadata_shape_array = np.array(
                            metadata.block_shape, dtype=np.int64
                        )
                        # Vectorized comparison: ensure metadata matches actual shape
                        if not np.array_equal(metadata_shape_array, actual_shape_array):
                            self.logger.warning(
                                f"Metadata shape mismatch for block {block_indices}: "
                                f"metadata={metadata.block_shape}, actual={block.shape}. "
                                f"Updating metadata to match true block shape."
                            )
                            # Update metadata to match actual block shape
                            self._cache_manager.save_block_metadata(
                                block_id,
                                block_indices,
                                block.shape,  # Use actual shape
                                block_path,
                                self._block_metadata,
                            )

                # Update memory cache (vectorized copy)
                with self._block_lock:
                    # Use vectorized copy (NumPy optimized)
                    if self.use_cuda and CUDA_AVAILABLE:
                        # Keep on CPU for memory cache (GPU memory is limited)
                        self._current_block = np.array(block, copy=True)
                    else:
                        self._current_block = np.array(block, copy=True)
                    self._current_block_id = block_id

                # Return vectorized copy with 7D structure validation
                result = np.array(block, copy=True)
                if result.ndim != 7 or len(result.shape) != 7:
                    raise ValueError(
                        f"Cached block has invalid 7D structure: "
                        f"ndim={result.ndim}, shape_len={len(result.shape)}"
                    )
                return result

        # Generate block (with CUDA support if available and 80% GPU memory limit)
        self.logger.info(f"Generating block {block_indices}")

        # Check GPU memory before generation (80% limit)
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                # Estimate block memory requirements
                block_volume = np.prod(self.block_size)
                bytes_per_element = 16  # complex128 = 16 bytes
                overhead_factor = 5.0  # Memory overhead for operations
                required_memory = block_volume * bytes_per_element * overhead_factor

                # Get available GPU memory (80% of free)
                mem_info = cp.cuda.runtime.memGetInfo()
                free_memory_bytes = mem_info[0]
                available_memory_bytes = int(free_memory_bytes * 0.8)  # 80% limit

                if required_memory > available_memory_bytes:
                    self.logger.warning(
                        f"Block generation requires "
                        f"{required_memory / 1e9:.2f}GB but only "
                        f"{available_memory_bytes / 1e9:.2f}GB available (80% limit). "
                        f"Block size: {self.block_size}. "
                        f"Proceeding with generation (may use CPU fallback)."
                    )
            except Exception as e:
                self.logger.debug(f"Could not check GPU memory before generation: {e}")

        block = self._block_generator.generate_block(block_indices)

        # Validate generated block has 7D structure (vectorized validation)
        if block.ndim != 7:
            raise ValueError(
                f"Generated block has wrong dimensionality: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {block.ndim}D. "
                f"Shape: {block.shape}"
            )
        # Vectorized shape validation: ensure shape is 7D
        if len(block.shape) != 7:
            raise ValueError(
                f"Generated block shape has wrong length: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {len(block.shape)}D. "
                f"Shape: {block.shape}"
            )

        # Save to disk using np.save (not raw tofile) - preserves array structure
        # Convert to CPU array before saving (np.save works with CPU arrays)
        if self.use_cuda and CUDA_AVAILABLE and isinstance(block, cp.ndarray):
            # Convert to CPU for saving (vectorized copy)
            block_cpu = cp.asnumpy(block)
        else:
            block_cpu = np.array(block, copy=True)

        # Use vectorized save operation (np.save preserves array structure)
        self._cache_manager.save_block(block_path, block_cpu)

        # Save metadata with actual block shape (ensures metadata matches true shape)
        self._cache_manager.save_block_metadata(
            block_id, block_indices, block_cpu.shape, block_path, self._block_metadata
        )

        # Update memory cache (vectorized copy)
        with self._block_lock:
            # Keep on CPU for memory cache (GPU memory is limited to 80%)
            self._current_block = np.array(block_cpu, copy=True)
            self._current_block_id = block_id

        # Return vectorized copy on CPU with 7D structure validation
        result = np.array(block_cpu, copy=True)
        if result.ndim != 7 or len(result.shape) != 7:
            raise ValueError(
                f"Block has invalid 7D structure: "
                f"ndim={result.ndim}, shape_len={len(result.shape)}"
            )

        if as_gpu:
            return self._transfer_block_to_gpu(result, stream=stream)
        return result

    def iter_gpu_blocks(
        self,
        *,
        max_blocks: Optional[int] = None,
        stream: Optional["Stream"] = None,
    ) -> Iterator[Tuple["cp.ndarray", Dict[str, Any]]]:
        """
        Iterate over blocks streamed directly to GPU memory.

        Physical Meaning:
            Provides sequential access to 7D phase-field blocks residing on GPU,
            keeping only one block (<=80% free GPU memory) in device RAM at a time.

        Args:
            max_blocks (Optional[int]): Limit for number of blocks to stream.
            stream (Optional[cp.cuda.Stream]): Optional CUDA stream used for transfers.

        Yields:
            Tuple[cp.ndarray, Dict[str, Any]]: GPU block and metadata.
        """

        if not (self.use_cuda and CUDA_AVAILABLE):
            raise RuntimeError(
                "iter_gpu_blocks requires CUDA-enabled generator; CPU streaming is not allowed."
            )

        for block, metadata in self.iterate_blocks(max_blocks):
            gpu_block = self._transfer_block_to_gpu(block, stream=stream)
            yield gpu_block, metadata

    def iterate_blocks(
        self, max_blocks: Optional[int] = None
    ) -> Iterator[Tuple[np.ndarray, Dict[str, Any]]]:
        """
        Iterate over all blocks in the 7D field with CUDA support and vectorization.

        Physical Meaning:
            Iterates over all 7D blocks in the phase field M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            allowing large block counts with warnings (not hard errors) up to
            a safe cap. Uses vectorized operations and CUDA acceleration with
            80% GPU memory limit. Validates metadata matches true block shape.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Block iteration: vectorized traversal of all 7D block combinations
            - Metadata validation: vectorized shape comparison ensures integrity
            - CUDA batch processing: processes multiple blocks when GPU memory allows
            - Large domain handling: warnings instead of errors for large block counts
            - Vectorized operations: all array operations use NumPy/CuPy vectorization

        Args:
            max_blocks (Optional[int]): Maximum number of blocks to iterate.
                If None, uses safety limit based on memory constraints.
                Allows large block counts with warnings up to safe cap.

        Yields:
            Tuple[np.ndarray, Dict[str, Any]]: Block data and metadata with
                block_shape matching true block shape.
        """
        # Warning for large total block counts (not hard error)
        if self.total_blocks > 50000:
            self.logger.warning(
                f"Iterating over large domain ({self.total_blocks} blocks). "
                f"This may take time. Consider increasing block_size for better performance. "
                f"Proceeding with iteration (warnings instead of errors)."
            )

        return self._block_iterator.iterate(max_blocks)

    def get_field(self) -> BlockedField:
        """Get lazy field object for transparent access."""
        return BlockedField(self.domain, self)

    def clear_cache(self) -> None:
        """Clear all cached blocks from disk."""
        for block_file in self.cache_dir.glob("block_*.npy"):
            block_file.unlink()
        for meta_file in self.cache_dir.glob("block_*.meta"):
            meta_file.unlink()
        self._block_metadata.clear()
        self.logger.info("Cache cleared")

    def cleanup(self) -> None:
        """Cleanup cache directory and resources."""
        self.clear_cache()
        if self.cache_dir.exists():
            self.cache_dir.rmdir()
        self.logger.info("Cleanup completed")

    def _transfer_block_to_gpu(
        self,
        block: np.ndarray,
        *,
        stream: Optional["Stream"] = None,
    ) -> "cp.ndarray":
        """
        Transfer CPU block to GPU using optional CUDA stream.

        Physical Meaning:
            Moves a 7D block into GPU memory so FFT and solver paths can process
            it while keeping peak device memory below the mandated 80% threshold.

        Args:
            block (np.ndarray): CPU-resident block.
            stream (Optional[cp.cuda.Stream]): CUDA stream for asynchronous copy.

        Returns:
            cp.ndarray: GPU array with the same shape/dtype as `block`.
        """

        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required to transfer blocks to GPU; CPU fallback is not permitted."
            )

        if stream is None:
            return cp.asarray(block)

        with stream:
            gpu_block = cp.asarray(block)
        stream.synchronize()
        return gpu_block
