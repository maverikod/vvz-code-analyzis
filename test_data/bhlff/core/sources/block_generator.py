"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block generator for 7D field blocks with CUDA support.

This module provides block generation functionality for 7D field blocks,
including vectorized operations and CUDA acceleration with 80% GPU memory limit.

Physical Meaning:
    Generates individual 7D blocks of phase fields by calling field generators
    with appropriate domain slices. Supports CUDA acceleration for vectorized
    7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Block boundaries: [start_i, end_i) for each dimension i ∈ [0,6]
    - Block shape: (end_i - start_i) for each dimension
    - Vectorized computation of boundaries
    - Spatial dimensions (0,1,2): ℝ³ₓ
    - Phase dimensions (3,4,5): 𝕋³_φ
    - Temporal dimension (6): ℝₜ

Example:
    >>> generator = BlockGenerator(domain, field_generator, block_size, use_cuda)
    >>> block = generator.generate_block(block_indices)
"""

import numpy as np
import logging
from typing import Dict, Any, Callable, Tuple, Union

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..domain import Domain
from ...utils.gpu_memory_monitor import GPUMemoryMonitor


class BlockGenerator:
    """
    Block generator for 7D field blocks with CUDA support.

    Physical Meaning:
        Generates individual 7D blocks by computing block boundaries and
        calling field generators. Supports CUDA acceleration with 80% GPU
        memory limit and vectorized operations for 7D structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Block boundaries computed vectorized: block_start = indices * size
        - Block shape: block_end - block_start
        - Ensures 7D structure preservation

    Attributes:
        domain (Domain): Computational domain.
        field_generator (Callable): Field generator function.
        block_size (Tuple[int, ...]): Block size per dimension (7-tuple).
        use_cuda (bool): Whether to use CUDA acceleration.
        config (Dict[str, Any]): Generator configuration.
        logger (logging.Logger): Logger instance.
    """

    def __init__(
        self,
        domain: Domain,
        field_generator: Callable[[Domain, Dict[str, Any], Dict[str, Any]], np.ndarray],
        block_size: Tuple[int, ...],
        use_cuda: bool,
        config: Dict[str, Any],
        logger: logging.Logger,
    ) -> None:
        """
        Initialize block generator.

        Args:
            domain (Domain): Computational domain.
            field_generator (Callable): Field generator function.
            block_size (Tuple[int, ...]): Block size per dimension (7-tuple).
            use_cuda (bool): Whether to use CUDA acceleration.
            config (Dict[str, Any]): Generator configuration.
            logger (logging.Logger): Logger instance.
        """
        self.domain = domain
        self.field_generator = field_generator
        self.block_size = block_size
        self.use_cuda = use_cuda
        self.config = config
        self.logger = logger
        
        # Initialize GPU memory monitor for unified memory management
        if self.use_cuda and CUDA_AVAILABLE:
            self.gpu_memory_monitor = GPUMemoryMonitor(
                warning_threshold=0.75,
                critical_threshold=0.9,
            )
        else:
            self.gpu_memory_monitor = None

    def generate_block(
        self, block_indices: Tuple[int, ...]
    ) -> Union[np.ndarray, "cp.ndarray"]:
        """
        Generate a single 7D block of the field with CUDA support.

        Physical Meaning:
            Generates the specified 7D block by calling the field generator
            with appropriate domain slice. Supports CUDA acceleration for
            vectorized 7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            Respects 80% GPU memory limit for block generation.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Block boundaries: [start_i, end_i) for each dimension i ∈ [0,6]
            - Block shape: (end_i - start_i) for each dimension
            - Ensures generated block has correct 7D shape
            - Spatial dimensions (0,1,2): ℝ³ₓ
            - Phase dimensions (3,4,5): 𝕋³_φ
            - Temporal dimension (6): ℝₜ

        Args:
            block_indices (Tuple[int, ...]): Block indices (7-tuple).

        Returns:
            Union[np.ndarray, cp.ndarray]: Generated field block (CPU or GPU).

        Raises:
            ValueError: If block_indices length != 7 or generated block is not 7D.
        """
        # Validate 7D structure: ensure block_indices has 7 elements
        if len(block_indices) != 7:
            raise ValueError(
                f"Expected 7D block indices for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(block_indices)}D: {block_indices}"
            )

        # Validate domain has 7D structure
        if len(self.domain.shape) != 7:
            raise ValueError(
                f"Expected 7D domain shape for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(self.domain.shape)}D: {self.domain.shape}"
            )

        # Validate block_size has 7D structure
        if len(self.block_size) != 7:
            raise ValueError(
                f"Expected 7D block size for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(self.block_size)}D: {self.block_size}"
            )

        # Compute block boundaries using vectorized operations (7D)
        # Use numpy array operations for efficiency
        block_indices_array = np.array(block_indices, dtype=np.int64)
        domain_shape_array = np.array(self.domain.shape, dtype=np.int64)
        block_size_array = np.array(self.block_size, dtype=np.int64)

        # Vectorized computation: block_start = block_indices * block_size
        block_start_array = block_indices_array * block_size_array
        # Vectorized computation: block_end = min(block_start + block_size, domain_shape)
        block_end_array = np.minimum(
            block_start_array + block_size_array, domain_shape_array
        )
        # Vectorized computation: block_shape = block_end - block_start
        block_shape_array = block_end_array - block_start_array

        # Convert to tuples for compatibility
        block_start = tuple(block_start_array.tolist())
        block_end = tuple(block_end_array.tolist())
        block_shape = tuple(block_shape_array.tolist())

        # Validate computed block_shape has 7D structure
        if len(block_shape) != 7:
            raise ValueError(
                f"Computed block shape has wrong dimensionality: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, "
                f"got {len(block_shape)}D: {block_shape}"
            )

        # Check GPU memory limit (80%) if CUDA is enabled using unified monitor
        if self.use_cuda and CUDA_AVAILABLE and self.gpu_memory_monitor is not None:
            try:
                # Calculate required memory for block generation
                bytes_per_element = 16  # complex128 = 16 bytes
                overhead_factor = 5.0  # Memory overhead for operations
                block_elements = np.prod(block_shape_array)
                required_memory = block_elements * bytes_per_element * overhead_factor

                # Get available GPU memory (80% of free) using unified monitor
                available_memory_bytes = self.gpu_memory_monitor.get_available_memory(
                    memory_ratio=0.8
                )

                if required_memory > available_memory_bytes:
                    self.logger.warning(
                        f"Block generation requires "
                        f"{required_memory / 1e9:.2f}GB "
                        f"but only {available_memory_bytes / 1e9:.2f}GB "
                        f"available (80% limit). "
                        f"Block shape: {block_shape}. "
                        f"Consider reducing block_size."
                    )
            except Exception as e:
                self.logger.debug(
                    f"Could not check GPU memory for block generation: {e}"
                )

        # Create domain slice configuration with 7D structure
        slice_config = {
            "start": block_start,  # 7-tuple
            "end": block_end,  # 7-tuple
            "shape": block_shape,  # 7-tuple
            "use_cuda": self.use_cuda,  # Pass CUDA flag to generator
        }

        # Generate block using field generator
        block = self.field_generator(self.domain, slice_config, self.config)

        # Ensure correct 7D shape
        expected_shape = block_shape
        if block.shape != expected_shape:
            # Validate generated block dimensionality
            if block.ndim != 7:
                raise ValueError(
                    f"Generated block has wrong dimensionality: "
                    f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {block.ndim}D. "
                    f"Shape: {block.shape}, expected: {expected_shape}"
                )

            # Reshape or pad if needed using vectorized operations
            if block.size == np.prod(expected_shape):
                # Reshape if total size matches (vectorized reshape)
                if self.use_cuda and CUDA_AVAILABLE and isinstance(block, cp.ndarray):
                    block = block.reshape(expected_shape)
                else:
                    block = block.reshape(expected_shape)
            else:
                # Pad or crop to correct size using vectorized operations
                if self.use_cuda and CUDA_AVAILABLE:
                    # Use CuPy for GPU operations (vectorized)
                    if isinstance(block, cp.ndarray):
                        padded = cp.zeros(expected_shape, dtype=block.dtype)
                    else:
                        block = cp.asarray(block)
                        padded = cp.zeros(expected_shape, dtype=block.dtype)
                else:
                    # Use NumPy for CPU operations (vectorized)
                    padded = np.zeros(expected_shape, dtype=block.dtype)

                # Vectorized slicing and assignment (7D)
                slices = tuple(
                    slice(0, min(s, d)) for s, d in zip(block.shape, expected_shape)
                )
                padded[slices] = block[slices]  # Vectorized assignment
                block = padded

        # Final validation: ensure block has 7D structure
        if block.ndim != 7:
            raise ValueError(
                f"Final block has wrong dimensionality: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {block.ndim}D. "
                f"Shape: {block.shape}"
            )

        if len(block.shape) != 7:
            raise ValueError(
                f"Final block shape has wrong length: "
                f"expected 7D for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, got {len(block.shape)}D. "
                f"Shape: {block.shape}"
            )

        return block
