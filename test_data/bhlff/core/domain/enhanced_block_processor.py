"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Enhanced block processor for 7D BVP data processing.

This module implements an enhanced block processing system for 7D BVP computations
with intelligent memory management, adaptive block sizing, and efficient data flow.

Physical Meaning:
    Provides intelligent block-based processing for 7D phase field computations,
    enabling memory-efficient operations on large 7D space-time domains with
    adaptive block sizing based on available memory and processing capabilities.

Mathematical Foundation:
    Implements adaptive block decomposition of 7D space-time domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    with intelligent memory management and processing optimization.

Example:
    >>> processor = EnhancedBlockProcessor(domain, config)
    >>> result = processor.process_7d_field(field, operation="bvp_solve", level_c_context=True)
"""

import numpy as np
import logging
import gc
from typing import Dict, Any

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .block_processor import BlockProcessor
from .domain import Domain
from ...utils.memory_monitor import MemoryMonitor
from ...utils.gpu_memory_monitor import GPUMemoryMonitor
from ...utils.cpu_memory_monitor import CPUMemoryMonitor
from .enhanced_block_processing import ProcessingConfig, ProcessingMode
from .enhanced_block_processing.gpu_block_processor import GPUBlockProcessor
from .enhanced_block_processing.cpu_block_processor import CPUBlockProcessor
from .enhanced_block_processing.field_processing_strategy import FieldProcessingStrategy
from .enhanced_block_processing.field_processor import FieldProcessor
from .enhanced_block_processing_core import EnhancedBlockProcessorCore
from .enhanced_block_processing_utils import EnhancedBlockProcessorUtils


class EnhancedBlockProcessor:
    """
    Enhanced block processor for 7D BVP data processing.

    Physical Meaning:
        Provides intelligent block-based processing for 7D phase field computations
        with adaptive memory management and processing optimization.
        For Level C contexts, enforces GPU-only execution with 7D operations.

    Mathematical Foundation:
        Implements adaptive block decomposition with intelligent memory management
        for efficient 7D BVP computations.
    """

    def __init__(self, domain: Domain, config: ProcessingConfig = None):
        """
        Initialize enhanced block processor.

        Physical Meaning:
            Sets up enhanced block processing system with intelligent memory
            management and adaptive block sizing for 7D BVP computations.

        Args:
            domain (Domain): 7D computational domain.
            config (ProcessingConfig): Processing configuration.
        """
        self.domain = domain
        self.config = config or ProcessingConfig()
        self.logger = logging.getLogger(__name__)

        # Initialize memory monitoring
        self.memory_monitor = MemoryMonitor()
        # Initialize specialized GPU and CPU memory monitors
        self.gpu_memory_monitor = GPUMemoryMonitor(
            warning_threshold=0.75,
            critical_threshold=0.9,
        )
        self.cpu_memory_monitor = CPUMemoryMonitor(
            warning_threshold=0.75,
            critical_threshold=0.9,
        )

        # CUDA availability
        self.cuda_available = EnhancedBlockProcessorUtils.check_cuda_availability()

        # Initialize utility methods
        self.utils = EnhancedBlockProcessorUtils(
            domain, self.config, self.cuda_available, self.logger
        )

        # Initialize block processors
        self.gpu_processor = GPUBlockProcessor(self.cuda_available, self.logger)
        self.cpu_processor = CPUBlockProcessor(self.logger)

        # Initialize base block processor with optimal block size
        self.base_processor = BlockProcessor(
            domain, self.utils.calculate_optimal_block_size()
        )

        # Initialize field processing strategy handler
        self.processing_strategy = FieldProcessingStrategy(
            self.gpu_processor,
            self.cpu_processor,
            self.base_processor,
            self.cuda_available,
            self.logger,
        )

        # Initialize core processing methods
        self.core = EnhancedBlockProcessorCore(
            self.processing_strategy,
            self.cuda_available,
            self.config.mode,
            self.logger,
        )

        # Initialize field processor for internal processing methods
        self.field_processor = FieldProcessor(
            self.processing_strategy,
            self.base_processor,
            self.cuda_available,
            self.logger,
        )

        # Processing statistics
        self.stats = {
            "blocks_processed": 0,
            "memory_peak_usage": 0.0,
            "processing_time": 0.0,
            "fallback_count": 0,
        }

        self.logger.info(
            f"Enhanced block processor initialized: "
            f"mode={self.config.mode.value}, "
            f"cuda_available={self.cuda_available}"
        )

    def process_7d_field(
        self, field: np.ndarray, operation: str = "bvp_solve", **kwargs
    ) -> np.ndarray:
        """
        Process 7D field using enhanced block processing.

        Physical Meaning:
            Processes 7D phase field using intelligent block decomposition
            with adaptive memory management and processing optimization.
            For Level C contexts, enforces GPU-only execution with 7D operations
            (7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²), backpressure, and 80% GPU memory limit.
            All operations use vectorized CUDA kernels for optimal performance.

        Mathematical Foundation:
            Uses 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for all 7D operations.
            Implements block-based processing with:
            - Vectorized CUDA operations across all 7 dimensions
            - Backpressure management with 80% GPU memory usage limit
            - Optimal block tiling for 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ

        Args:
            field (np.ndarray): 7D phase field to process with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆).
            operation (str): Processing operation to perform.
            **kwargs: Additional operation parameters including:
                - level_c_context (bool): If True, requires GPU and disables CPU fallback.
                    Forces 7D operations, backpressure, and 80% GPU memory limit.
                - use_7d_operations (bool): If True, uses 7D-specific operations (default: True).
                - use_backpressure (bool): Enable backpressure management (default: True for Level C).

        Returns:
            np.ndarray: Processed 7D field.

        Raises:
            RuntimeError: If Level C context is requested but CUDA is not available.
            ValueError: If field is not 7D.
        """
        # Validate 7D field structure
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for processing, got {field.ndim}D. "
                f"Shape: {field.shape}. 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ required."
            )

        # Check for Level C context
        level_c_context = kwargs.get("level_c_context", False)

        self.logger.info(
            f"Processing 7D field: shape={field.shape}, operation={operation}, "
            f"level_c_context={level_c_context}"
        )

        # Level C requires CUDA - no CPU fallback (project policy)
        if level_c_context:
            if not self.cuda_available:
                raise RuntimeError(
                    "Level C context requires CUDA but GPU is not available. "
                    "Level C does not support CPU fallback. Please ensure CUDA "
                    "is available and GPU is accessible."
                )

            # Enforce 7D operations, backpressure, and 80% GPU memory limit for Level C
            kwargs["use_7d_operations"] = True
            kwargs["use_backpressure"] = True
            kwargs["level_c_context"] = True  # Ensure flag is set

            # Optimize block size for Level C with 80% GPU memory limit
            self.optimize_for_field(field)

            self.logger.info(
                "Level C context: enforcing GPU-only processing with 7D operations "
                "(7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²), backpressure, and 80% GPU memory limit"
            )

            # Use GPU-only processing with explicit 7D operations and backpressure
            result = self.processing_strategy.process_gpu_only(
                field, operation, **kwargs
            )
            self.stats["blocks_processed"] = getattr(
                self.processing_strategy, "_last_block_count", 0
            )
            return result

        # Check memory requirements
        # For Level C, never use fallback - must fail if memory insufficient
        # Level C processing already handled above, so this check is for non-Level C
        if not self.utils.check_memory_requirements(
            field, level_c_context=level_c_context
        ):
            # For non-Level C, use fallback only if explicitly enabled
            non_level_c = kwargs.get("non_level_c", False)
            if not non_level_c:
                self.logger.error(
                    "Insufficient memory for processing. CPU fallback is disabled "
                    "by default. Set non_level_c=True to explicitly enable CPU fallback."
                )
                raise RuntimeError(
                    "Insufficient memory for processing. CPU fallback is disabled by default. "
                    "Set non_level_c=True in kwargs to explicitly enable CPU fallback."
                )
            self.logger.warning(
                "Insufficient memory, using fallback processing (non_level_c=True explicitly set)"
            )
            result = self.field_processor.fallback_processing(
                field,
                operation,
                self.config.min_block_size,
                **kwargs,
            )
            self.stats["blocks_processed"] = getattr(
                self.processing_strategy, "_last_block_count", 0
            )
            self.stats["fallback_count"] += 1
            return result

        # For non-Level C, use internal processing method with 7D operations
        # This method handles CPU fallback only if explicitly enabled
        # Default to 7D operations for optimal performance with vectorization
        kwargs.setdefault("use_7d_operations", True)
        result = self.field_processor.process_field(field, operation, **kwargs)
        self.stats["blocks_processed"] = getattr(
            self.processing_strategy, "_last_block_count", 0
        )
        return result

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            **self.stats,
            "cuda_available": self.cuda_available,
            "current_block_size": self.base_processor.block_size,
            "memory_usage": self.memory_monitor.get_cpu_memory_usage(),
        }

    def optimize_for_field(self, field: np.ndarray) -> None:
        """
        Optimize processor settings for a specific 7D field.

        Physical Meaning:
            Optimizes processor configuration based on 7D field characteristics
            to maximize processing efficiency with vectorized CUDA operations.
            For 7D fields, uses 7D-specific optimization with 80% GPU memory limit.
            Considers 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ for optimal block sizing.
            All operations use 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² with vectorization.

        Mathematical Foundation:
            For 7D field with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - GPU: uses 80% of free GPU memory with 7D block tiling
            - Block size optimized for 7D Laplacian operations: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
            - Vectorized operations across all 7 dimensions for optimal GPU utilization
            - Optimal block tiling preserves 7D geometry M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ

        Args:
            field (np.ndarray): 7D field to optimize for with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆).

        Raises:
            ValueError: If field is not 7D.
            RuntimeError: If CUDA optimization fails for Level C context.
        """
        # Validate 7D field structure
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for optimization, got {field.ndim}D. "
                f"Shape: {field.shape}. 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ required."
            )

        field_size = field.nbytes / (1024**3)  # GB

        # For CUDA, use GPU memory-based optimization with 80% limit
        # This is critical for Level C contexts and optimal 7D processing
        if self.cuda_available:
            try:
                if CUDA_AVAILABLE:
                    # Check GPU memory before optimization using specialized monitor
                    try:
                        gpu_mem_info = self.gpu_memory_monitor.check_memory()
                        self.logger.debug(
                            f"GPU memory check: {gpu_mem_info['usage_ratio']:.1%} used, "
                            f"{gpu_mem_info['free'] / (1024**3):.2f} GB free"
                        )
                    except MemoryError as e:
                        self.logger.warning(f"GPU memory warning: {e}")
                    
                    # Use 7D block tiling optimization with 80% GPU memory
                    # This ensures optimal block size for 7D Laplacian operations
                    optimal_size = self.utils.calculate_optimal_block_size()
                    self.base_processor.block_size = optimal_size

                    # Verify GPU memory usage is within 80% limit using monitor
                    if CUDA_AVAILABLE:
                        available_memory_gpu = self.gpu_memory_monitor.get_available_memory(
                            memory_ratio=0.8
                        ) / (1024**3)  # GB

                        # Estimate memory usage for optimal block size
                        block_volume = optimal_size**7  # 7D block
                        element_size = 16  # complex128 = 16 bytes
                        block_memory = (block_volume * element_size) / (1024**3)  # GB
                        # Processing overhead: ~5x for 7D operations (FFT, Laplacian, etc.)
                        processing_memory = block_memory * 5

                        if processing_memory > available_memory_gpu:
                            self.logger.warning(
                                f"Block size {optimal_size} may exceed 80% GPU memory limit. "
                                f"Estimated: {processing_memory:.2f} GB > {available_memory_gpu:.2f} GB. "
                                f"Reducing block size to stay within limit."
                            )
                            # Reduce block size to stay within 80% limit
                            max_block_volume = (available_memory_gpu * 1024**3) / (
                                element_size * 5
                            )
                            optimal_size = max(4, int(max_block_volume ** (1.0 / 7.0)))
                            self.base_processor.block_size = optimal_size

                    self.logger.info(
                        f"Optimized 7D block size using GPU: {self.base_processor.block_size} "
                        f"(80% GPU memory limit, field_size={field_size:.2f} GB, "
                        f"7D Laplacian operations with vectorization)"
                    )
                    return
            except Exception as e:
                self.logger.error(
                    f"Failed to optimize using GPU memory: {e}. "
                    f"For Level C contexts, GPU optimization is required."
                )
                # For Level C, raise error instead of falling back
                raise RuntimeError(
                    f"GPU optimization failed for 7D field: {e}. "
                    f"Level C requires GPU optimization with 80% memory limit."
                ) from e

        # CPU fallback: adjust block size based on field size
        # For 7D fields, use smaller blocks to respect memory constraints
        # Note: CPU processing should not be used for Level C contexts
        if field_size < 0.1:  # Small field
            self.base_processor.block_size = min(32, self.config.max_block_size)
        elif field_size < 1.0:  # Medium field
            self.base_processor.block_size = min(16, self.config.max_block_size)
        else:  # Large field
            self.base_processor.block_size = self.config.min_block_size

        self.logger.info(
            f"Optimized block size for 7D field (CPU fallback): "
            f"{self.base_processor.block_size} (field_size={field_size:.2f} GB)"
        )

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.cuda_available and CUDA_AVAILABLE:
            # Use GPU memory monitor for cleanup
            self.gpu_memory_monitor.free_all_blocks()

        gc.collect()
        self.logger.info("Enhanced block processor cleaned up")
