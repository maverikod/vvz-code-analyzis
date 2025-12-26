"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field processing methods for enhanced block processor.

This module implements internal field processing methods with GPU preference,
guarded CPU fallback, and Level C context enforcement for 7D BVP computations.
"""

import numpy as np
import logging
from typing import Dict, Any

from .field_processing_strategy import FieldProcessingStrategy
from ..block_processor import BlockProcessor


class FieldProcessor:
    """
    Internal field processor for enhanced block processor.

    Physical Meaning:
        Provides internal field processing methods for 7D phase field computations
        with GPU preference, guarded CPU fallback, and Level C context enforcement.
        All operations use 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² with vectorization.

    Mathematical Foundation:
        Implements processing strategies with 7D operations:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - GPU processing with 80% memory usage limit
        - Backpressure management for optimal GPU utilization
    """

    def __init__(
        self,
        processing_strategy: FieldProcessingStrategy,
        base_processor: BlockProcessor,
        cuda_available: bool,
        logger: logging.Logger,
    ):
        """
        Initialize field processor.

        Args:
            processing_strategy (FieldProcessingStrategy): Field processing strategy handler.
            base_processor (BlockProcessor): Base block processor.
            cuda_available (bool): Whether CUDA is available.
            logger (logging.Logger): Logger instance.
        """
        self.processing_strategy = processing_strategy
        self.base_processor = base_processor
        self.cuda_available = cuda_available
        self.logger = logger

    def process_field(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """
        Internal method to process field with GPU preference and guarded CPU fallback.

        Physical Meaning:
            Processes 7D field using GPU-accelerated block processing with 7D operations
            (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²) and vectorization. For Level C contexts,
            GPU is required with 7D operations and backpressure. CPU fallback is only
            allowed if explicitly enabled via non_level_c flag.

        Mathematical Foundation:
            Uses 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for all 7D operations.
            Enforces 80% GPU memory usage with backpressure for Level C.
            All operations use vectorized CUDA kernels for optimal performance.

        Args:
            field (np.ndarray): 7D field to process with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
            operation (str): Operation to perform.
            **kwargs: Additional parameters including:
                - level_c_context (bool): If True, disables CPU fallback and enforces 7D operations.
                - non_level_c (bool): If True, explicitly allows CPU fallback (Level C override).
                - use_7d_operations (bool): Use 7D-specific operations (default: True).
                - use_backpressure (bool): Enable backpressure management (default: True for Level C).

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If Level C context is active and GPU processing fails.
            ValueError: If field is not 7D.
        """
        # Validate 7D field structure
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for processing, got {field.ndim}D. "
                f"Shape: {field.shape}. 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ required."
            )

        level_c_context = kwargs.get("level_c_context", False)
        non_level_c = kwargs.get("non_level_c", False)

        # For Level C, enforce GPU-only with 7D operations - no CPU fallback
        # This is critical project policy: Level C requires GPU with 7D operations
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
                "(7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²), backpressure, and 80% GPU memory limit"
            )
            return self.processing_strategy.process_gpu_only(field, operation, **kwargs)

        # For non-Level C, choose strategy adaptively with GPU preference
        # Default to 7D operations for optimal performance with vectorization
        kwargs.setdefault("use_7d_operations", True)

        # CUDA is required - NO CPU fallback allowed
        if not self.cuda_available:
            from ...exceptions import CUDANotAvailableError
            raise CUDANotAvailableError(
                "CUDA is required for field processing. CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        # Try GPU processing
        try:
            return self.processing_strategy.process_gpu_preferred(
                field, operation, **kwargs
            )
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

    def fallback_processing(
        self, field: np.ndarray, operation: str, min_block_size: int, **kwargs
    ) -> np.ndarray:
        """
        Fallback processing for memory-constrained situations.

        Physical Meaning:
            Provides fallback processing when memory is constrained. For Level C
            contexts, this method raises an error instead of falling back to CPU,
            as Level C requires GPU execution with 7D operations and backpressure.
            CPU fallback is only allowed if explicitly enabled via non_level_c flag.

        Mathematical Foundation:
            This method should not be used for Level C contexts. Level C requires
            7D operations with 80% GPU memory usage and backpressure management.
            For non-Level C contexts, uses minimal block size for CPU processing.

        Args:
            field (np.ndarray): 7D field to process with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
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
        # This is critical: Level C requires GPU with 7D operations and backpressure
        if level_c_context:
            raise RuntimeError(
                "Level C context does not support CPU fallback. "
                "GPU processing with 7D operations (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²) "
                "and backpressure is required. "
                "Please ensure sufficient GPU memory (80% usage rule) or reduce field size. "
                "Level C enforces GPU-only execution with vectorized CUDA operations."
            )

        # Validate 7D field structure
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for fallback processing, got {field.ndim}D. "
                f"Shape: {field.shape}. 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ required."
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
                "Project policy prefers GPU processing with backpressure and vectorization."
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
            result = self.processing_strategy.process_cpu_optimized(field, operation, **kwargs)
        finally:
            # Restore original block size
            self.base_processor.block_size = original_block_size

        return result

