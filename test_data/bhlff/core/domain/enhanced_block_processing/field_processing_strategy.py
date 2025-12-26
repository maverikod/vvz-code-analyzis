"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field processing strategies for enhanced block processing.

This module implements processing strategies for 7D field processing
with GPU preference, CPU fallback control, and Level C context enforcement.
"""

import numpy as np
import logging
from typing import Dict, Any

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .gpu_block_processor import GPUBlockProcessor
from .cpu_block_processor import CPUBlockProcessor
from ..block_processor import BlockProcessor
from ...exceptions import CUDANotAvailableError, InsufficientGPUMemoryError


class FieldProcessingStrategy:
    """
    Field processing strategy handler for 7D fields.

    Physical Meaning:
        Provides processing strategies for 7D phase field computations
        with GPU preference, CPU fallback control, and Level C context
        enforcement. For Level C contexts, enforces GPU-only execution
        with 7D operations and backpressure.

    Mathematical Foundation:
        Implements processing strategies with 7D Laplacian:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - GPU processing with 80% memory usage limit
        - Backpressure management for optimal GPU utilization
    """

    def __init__(
        self,
        gpu_processor: GPUBlockProcessor,
        cpu_processor: CPUBlockProcessor,
        base_processor: BlockProcessor,
        cuda_available: bool,
        logger: logging.Logger = None,
    ):
        """
        Initialize field processing strategy handler.

        Physical Meaning:
            Sets up processing strategy handler with GPU and CPU processors
            for 7D field processing with Level C context support.

        Args:
            gpu_processor (GPUBlockProcessor): GPU block processor.
            cpu_processor (CPUBlockProcessor): CPU block processor.
            base_processor (BlockProcessor): Base block processor.
            cuda_available (bool): Whether CUDA is available.
            logger (logging.Logger): Logger instance.
        """
        self.gpu_processor = gpu_processor
        self.cpu_processor = cpu_processor
        self.base_processor = base_processor
        self.cuda_available = cuda_available
        self.logger = logger or logging.getLogger(__name__)

    def process_gpu_preferred(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """
        Process field with GPU preference and conditional CPU fallback.

        Physical Meaning:
            Attempts GPU processing first with 7D operations and backpressure
            management. For Level C contexts, GPU is required with 7D operations
            and CPU fallback is disabled. For non-Level C, CPU fallback is allowed
            only if explicitly enabled via non_level_c flag.

        Mathematical Foundation:
            Uses 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for all 7D operations.
            Enforces 80% GPU memory usage with backpressure for Level C.

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            **kwargs: Additional parameters including:
                - level_c_context (bool): If True, disables CPU fallback and enforces 7D operations.
                - non_level_c (bool): If True, explicitly allows CPU fallback (Level C override).
                - use_7d_operations (bool): Use 7D-specific operations (default: True).

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If Level C context is active and GPU processing fails.
            ValueError: If field is not 7D.
        """
        level_c_context = kwargs.get("level_c_context", False)
        non_level_c = kwargs.get("non_level_c", False)

        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        # For Level C, enforce GPU-only with 7D operations - no CPU fallback
        if level_c_context:
            if not self.cuda_available:
                raise RuntimeError(
                    "Level C context requires GPU but CUDA is not available. "
                    "Level C does not support CPU fallback. Please ensure CUDA "
                    "is available and GPU is accessible."
                )
            # Level C always uses GPU with 7D operations and backpressure - no fallback
            kwargs["use_7d_operations"] = True
            kwargs["use_backpressure"] = True
            self.logger.info(
                "Level C context: enforcing GPU-only processing with 7D operations "
                "and backpressure (80% GPU memory limit)"
            )
            return self.process_gpu_only(field, operation, **kwargs)

        # CUDA is required - NO CPU fallback allowed
        # All operations must use GPU
        if not self.cuda_available:
            raise CUDANotAvailableError(
                "CUDA is required for field processing. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        try:
            # Default to 7D operations for optimal performance
            kwargs.setdefault("use_7d_operations", True)
            return self.process_gpu_only(field, operation, **kwargs)
        except (CUDANotAvailableError, InsufficientGPUMemoryError):
            # Re-raise CUDA and memory errors as-is
            raise
        except Exception as e:
            # CPU fallback is NOT ALLOWED - raise CUDA error
            self.logger.error(
                f"GPU processing failed: {e}. CPU fallback is NOT ALLOWED. "
                f"Please ensure CUDA is properly configured."
            )
            raise CUDANotAvailableError(
                f"GPU processing failed: {e}. CUDA is required. "
                f"CPU fallback is NOT ALLOWED in this project. "
                f"Please ensure CUDA is properly configured and GPU is available."
            ) from e

    def process_gpu_only(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """
        Process field using GPU only with 7D operations.

        Physical Meaning:
            Processes 7D field on GPU using vectorized CUDA operations
            and 7D-specific operations (7D Laplacian). For Level C contexts,
            always uses 7D operations with optimal memory management (80% rule).

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            **kwargs: Additional parameters including:
                - level_c_context (bool): If True, enforces 7D operations.
                - use_7d_operations (bool): Use 7D-specific operations (default: True for Level C).
                - use_backpressure (bool): Enable backpressure management.

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If CUDA is not available or field is not 7D.
        """
        if not self.cuda_available:
            raise RuntimeError("GPU processing requested but CUDA not available")

        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for GPU processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        # For Level C, always use 7D operations with backpressure
        level_c_context = kwargs.get("level_c_context", False)
        use_backpressure = kwargs.get("use_backpressure", level_c_context)

        if level_c_context:
            kwargs["use_7d_operations"] = True
            kwargs["use_backpressure"] = True
            self.logger.info(
                "Level C context: enforcing 7D operations with backpressure "
                "and 80% GPU memory usage limit"
            )
        else:
            # Default to 7D operations if not explicitly disabled
            kwargs.setdefault("use_7d_operations", True)
            # Enable backpressure for optimal GPU memory management
            kwargs.setdefault("use_backpressure", use_backpressure)

        # Process with GPU block processor using 7D operations and backpressure
        # The GPU processor handles backpressure internally for optimal memory usage
        result, block_count = self.gpu_processor.process_blocks(
            field, operation, self.base_processor.iterate_blocks(), **kwargs
        )

        # Store block count for statistics tracking
        self._last_block_count = block_count

        # Log processing statistics for Level C
        if level_c_context:
            self.logger.info(
                f"Level C processing completed: {block_count} blocks processed "
                f"with 7D operations and backpressure"
            )

        return result

    def process_cpu_optimized(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """
        Process field using CPU with optimizations.

        Physical Meaning:
            Processes 7D field on CPU using vectorized NumPy operations
            and 7D-specific operations (7D Laplacian). This method should
            NOT be called for Level C contexts.

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            **kwargs: Additional parameters.

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If called for Level C context (should not happen).
        """
        # Safety check: Level C should never reach CPU processing
        level_c_context = kwargs.get("level_c_context", False)
        if level_c_context:
            raise RuntimeError(
                "Level C context reached CPU processing - this should not happen. "
                "Level C requires GPU processing only."
            )

        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for CPU processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        result, block_count = self.cpu_processor.process_blocks(
            field, operation, self.base_processor.iterate_blocks(), **kwargs
        )
        # Store block count for statistics tracking
        self._last_block_count = block_count
        return result

    def process_fallback(
        self, field: np.ndarray, operation: str, min_block_size: int, **kwargs
    ) -> np.ndarray:
        """
        Fallback processing for memory-constrained situations.

        Physical Meaning:
            Provides fallback processing when memory is constrained. For Level C
            contexts, this method raises an error instead of falling back to CPU,
            as Level C requires GPU execution with 7D operations and backpressure.

        Mathematical Foundation:
            This method should not be used for Level C contexts. Level C requires
            7D operations with 80% GPU memory usage and backpressure management.

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            min_block_size (int): Minimum block size for fallback.
            **kwargs: Additional parameters including:
                - level_c_context (bool): If True, disables CPU fallback.
                - non_level_c (bool): If True, explicitly allows CPU fallback (Level C override).

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If Level C context is requested (CPU fallback disabled).
            ValueError: If field is not 7D.
        """
        level_c_context = kwargs.get("level_c_context", False)
        non_level_c = kwargs.get("non_level_c", False)

        # Level C does not allow CPU fallback - enforce project policy
        if level_c_context:
            raise RuntimeError(
                "Level C context does not support CPU fallback. "
                "GPU processing with 7D operations and backpressure is required. "
                "Please ensure sufficient GPU memory (80% usage rule) or reduce field size. "
                "Level C enforces GPU-only execution with 7D Laplacian operations."
            )

        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for fallback processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        # CPU fallback is guarded behind explicit non_level_c flag
        # This enforces project policy: prefer GPU, guard CPU fallback
        if not non_level_c:
            self.logger.error(
                "CPU fallback processing is disabled by default. "
                "Set non_level_c=True to explicitly enable CPU fallback."
            )
            raise RuntimeError(
                "CPU fallback processing is disabled by default. "
                "Set non_level_c=True in kwargs to explicitly enable CPU fallback. "
                "Project policy prefers GPU processing with backpressure."
            )

        self.logger.warning(
            "Using CPU fallback processing due to memory constraints "
            "(non_level_c=True explicitly set)"
        )

        # Use minimal block size for CPU processing
        original_block_size = self.base_processor.block_size
        self.base_processor.block_size = min_block_size

        try:
            # Ensure Level C flag is not set for CPU processing
            kwargs["level_c_context"] = False
            result = self.process_cpu_optimized(field, operation, **kwargs)
        finally:
            # Restore original block size
            self.base_processor.block_size = original_block_size

        return result

