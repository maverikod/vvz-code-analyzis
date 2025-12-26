"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core processing methods for enhanced block processor.

This module implements core field processing methods for 7D BVP computations
with GPU preference, guarded CPU fallback, and Level C context enforcement.
"""

import numpy as np
import logging
from typing import Dict, Any

from .enhanced_block_processing import ProcessingMode
from .enhanced_block_processing.field_processing_strategy import FieldProcessingStrategy
from ..exceptions import CUDANotAvailableError, InsufficientGPUMemoryError


class EnhancedBlockProcessorCore:
    """
    Core processing methods for enhanced block processor.

    Physical Meaning:
        Provides core field processing methods for 7D phase field computations
        with GPU preference, guarded CPU fallback, and Level C context enforcement.
        All operations use 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ².

    Mathematical Foundation:
        Implements processing strategies with 7D operations:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - GPU processing with 80% memory usage limit
        - Backpressure management for optimal GPU utilization
    """

    def __init__(
        self,
        processing_strategy: FieldProcessingStrategy,
        cuda_available: bool,
        config_mode: ProcessingMode,
        logger: logging.Logger,
    ):
        """
        Initialize core processing methods.

        Args:
            processing_strategy (FieldProcessingStrategy): Field processing strategy handler.
            cuda_available (bool): Whether CUDA is available.
            config_mode (ProcessingMode): Processing mode configuration.
            logger (logging.Logger): Logger instance.
        """
        self.processing_strategy = processing_strategy
        self.cuda_available = cuda_available
        self.config_mode = config_mode
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
            RuntimeError: If GPU processing fails and CPU fallback is not explicitly enabled.
            ValueError: If field is not 7D.
        """
        # Validate 7D field
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for processing, got {field.ndim}D. "
                f"Shape: {field.shape}"
            )

        level_c_context = kwargs.get("level_c_context", False)
        non_level_c = kwargs.get("non_level_c", False)

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
            return self.processing_strategy.process_gpu_only(field, operation, **kwargs)

        # For non-Level C, choose strategy adaptively
        if self.config_mode == ProcessingMode.ADAPTIVE:
            strategy = self._choose_adaptive_strategy(field)
        else:
            strategy = self.config_mode

        # Process based on strategy with guarded CPU fallback
        try:
            # Default to 7D operations for optimal performance
            kwargs.setdefault("use_7d_operations", True)
            if strategy == ProcessingMode.GPU_PREFERRED and self.cuda_available:
                return self.processing_strategy.process_gpu_preferred(
                    field, operation, **kwargs
                )
            elif strategy == ProcessingMode.GPU_ONLY and self.cuda_available:
                return self.processing_strategy.process_gpu_only(field, operation, **kwargs)
            else:
                # CPU processing only if explicitly enabled
                if not non_level_c:
                    self.logger.error(
                        "CPU processing requested but CPU fallback is disabled by default. "
                        "Set non_level_c=True to explicitly enable CPU processing."
                    )
                    raise RuntimeError(
                        "CPU processing is disabled by default. "
                        "Set non_level_c=True in kwargs to explicitly enable CPU processing."
                    )
                return self.processing_strategy.process_cpu_optimized(
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
        self, field: np.ndarray, operation: str, min_block_size: int, base_processor, **kwargs
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

        Args:
            field (np.ndarray): 7D field to process.
            operation (str): Operation to perform.
            min_block_size (int): Minimum block size for fallback.
            base_processor: Base block processor instance.
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
        original_block_size = base_processor.block_size
        base_processor.block_size = min_block_size

        try:
            # Ensure Level C flag is not set for CPU processing
            kwargs["level_c_context"] = False
            result = self.processing_strategy.process_cpu_optimized(field, operation, **kwargs)
        finally:
            # Restore original block size
            base_processor.block_size = original_block_size

        return result

    def _choose_adaptive_strategy(self, field: np.ndarray) -> ProcessingMode:
        """
        Choose processing strategy based on field size and available resources.

        Physical Meaning:
            Intelligently selects the best processing strategy based on
            field characteristics and available computational resources.
            For 7D fields, prefers GPU with 7D operations.

        Args:
            field (np.ndarray): 7D field to process.

        Returns:
            ProcessingMode: Selected processing mode.
        """
        field_size = field.nbytes / (1024**3)  # GB

        # If field is small, prefer GPU for speed with 7D operations
        if field_size < 0.5 and self.cuda_available:
            return ProcessingMode.GPU_PREFERRED

        # If field is large, prefer GPU with 7D operations if available
        # CPU is only used if explicitly enabled via non_level_c flag
        elif field_size > 2.0:
            if self.cuda_available:
                return ProcessingMode.GPU_PREFERRED
            else:
                # CPU only if CUDA not available (but still guarded)
                return ProcessingMode.CPU_ONLY

        # Otherwise, use adaptive approach with GPU preference
        else:
            return ProcessingMode.GPU_PREFERRED if self.cuda_available else ProcessingMode.ADAPTIVE

