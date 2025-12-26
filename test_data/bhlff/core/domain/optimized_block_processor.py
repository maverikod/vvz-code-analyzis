"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimized block processor for 7D BVP data processing.

This module implements an optimized block processing system for 7D BVP computations
with intelligent memory management, adaptive block sizing, and efficient data flow.

Physical Meaning:
    Provides intelligent block-based processing for 7D phase field computations
    with adaptive memory management and processing optimization.

Mathematical Foundation:
    Implements adaptive block decomposition of 7D space-time domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    with intelligent memory management and processing optimization.

Example:
    >>> processor = OptimizedBlockProcessor(domain, config)
    >>> result = processor.process_7d_field(field, operation="bvp_solve")
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List, Callable
import logging
import time
import gc
from dataclasses import dataclass
from enum import Enum

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False

from .block_processor import BlockProcessor, BlockInfo
from .domain import Domain
from .optimal_block_size_calculator import OptimalBlockSizeCalculator
from ...utils.memory_monitor import MemoryMonitor
from ...utils.gpu_memory_monitor import GPUMemoryMonitor
from ...utils.cpu_memory_monitor import CPUMemoryMonitor


class ProcessingMode(Enum):
    """Processing mode for block operations."""

    CPU_ONLY = "cpu_only"
    GPU_PREFERRED = "gpu_preferred"
    GPU_ONLY = "gpu_only"
    ADAPTIVE = "adaptive"


@dataclass
class OptimizedConfig:
    """Configuration for optimized block processing."""

    # Block processing settings
    block_size: int = 8
    overlap_ratio: float = 0.1
    max_memory_usage: float = 0.7

    # Processing optimization
    enable_adaptive_sizing: bool = True
    enable_memory_optimization: bool = True
    enable_parallel_processing: bool = True
    enable_gpu_acceleration: bool = True

    # Performance settings
    batch_size: int = 4
    max_field_size_mb: float = 100.0  # Maximum field size in MB


class OptimizedBlockProcessor:
    """
    Optimized block processor for 7D BVP data processing.

    Physical Meaning:
        Provides intelligent block-based processing for 7D phase field computations
        with adaptive memory management and processing optimization.

    Mathematical Foundation:
        Implements adaptive block decomposition with intelligent memory management
        for efficient 7D BVP computations.
    """

    def __init__(self, domain: Domain, config: OptimizedConfig = None):
        """
        Initialize optimized block processor.

        Physical Meaning:
            Sets up optimized block processing system with intelligent memory
            management and adaptive block sizing for 7D BVP computations.

        Args:
            domain (Domain): 7D computational domain.
            config (OptimizedConfig): Processing configuration.
        """
        self.domain = domain
        self.config = config or OptimizedConfig()
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
        self.cuda_available = CUDA_AVAILABLE and self.config.enable_gpu_acceleration

        # Initialize unified block size calculator
        self._block_size_calculator = OptimalBlockSizeCalculator(
            gpu_memory_ratio=0.8  # Use 80% GPU memory (project requirement)
        )

        # Calculate optimal block size
        self.block_size = self._calculate_optimal_block_size()

        # Initialize base block processor
        self.base_processor = BlockProcessor(
            domain, self.block_size, int(self.block_size * self.config.overlap_ratio)
        )

        # Processing statistics
        self.stats = {
            "blocks_processed": 0,
            "memory_peak_usage": 0.0,
            "processing_time": 0.0,
            "gpu_usage": 0.0,
            "fallback_count": 0,
        }

        self.logger.info(
            f"Optimized block processor initialized: "
            f"block_size={self.block_size}, "
            f"cuda_available={self.cuda_available}"
        )

    def _calculate_optimal_block_size(self) -> int:
        """
        Calculate optimal block size based on available memory and domain size.

        Physical Meaning:
            Calculates optimal block size to maximize processing efficiency
            while staying within memory constraints. Uses unified
            OptimalBlockSizeCalculator for consistent 80% GPU memory usage.

        Returns:
            int: Optimal block size.
        """
        # Use unified block size calculator
        try:
            block_tiling = self._block_size_calculator.calculate_for_7d(
                domain_shape=self.domain.shape,
                dtype=np.complex128,
                overhead_factor=5.0,
            )
            # Use minimum block size from tiling
            optimal_size = min(block_tiling)
            
            # Apply config constraints
            optimal_size = min(optimal_size, self.config.block_size)
            optimal_size = max(optimal_size, 2)  # Minimum block size
            
            # Ensure it's reasonable for the domain
            for dim_size in self.domain.shape:
                optimal_size = min(optimal_size, dim_size)
            
            self.logger.info(
                f"Optimal block size (via unified calculator): {optimal_size} "
                f"(from tiling: {block_tiling}, GPU memory ratio: 80%)"
            )
            return optimal_size
        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size with unified calculator: {e}, "
                f"falling back to legacy calculation"
            )
            # Fallback to legacy calculation
            return self._calculate_optimal_block_size_legacy()
    
    def _calculate_optimal_block_size_legacy(self) -> int:
        """
        Legacy block size calculation (fallback).
        
        Physical Meaning:
            Legacy calculation method used as fallback when unified
            calculator fails.
            
        Returns:
            int: Optimal block size.
        """
        # Get available memory
        memory_stats = self.memory_monitor.get_cpu_memory_usage()
        available_memory_gb = memory_stats["available_mb"] / 1024.0

        # Calculate domain size
        domain_size = np.prod(self.domain.shape)
        element_size = 16  # complex128 = 16 bytes

        # Calculate maximum block size that fits in memory
        max_block_size = int(
            (available_memory_gb * 1024**3 / (element_size * 8))
            ** (1.0 / len(self.domain.shape))
        )

        # Apply constraints
        optimal_size = min(max_block_size, self.config.block_size)
        optimal_size = max(optimal_size, 2)  # Minimum block size

        # Ensure it's reasonable for the domain
        for dim_size in self.domain.shape:
            optimal_size = min(optimal_size, dim_size)

        self.logger.info(
            f"Optimal block size (legacy): {optimal_size} "
            f"(available memory: {available_memory_gb:.2f} GB)"
        )

        return optimal_size

    def process_7d_field(
        self, field: np.ndarray, operation: str = "bvp_solve", **kwargs
    ) -> np.ndarray:
        """
        Process 7D field using optimized block processing.

        Physical Meaning:
            Processes 7D phase field using intelligent block decomposition
            with adaptive memory management and processing optimization.

        Args:
            field (np.ndarray): 7D phase field to process.
            operation (str): Processing operation to perform.
            **kwargs: Additional operation parameters.

        Returns:
            np.ndarray: Processed 7D field.
        """
        self.logger.info(
            f"Processing 7D field: shape={field.shape}, operation={operation}"
        )

        start_time = time.time()

        # Check field size
        field_size_mb = field.nbytes / (1024**2)
        if field_size_mb > self.config.max_field_size_mb:
            self.logger.warning(
                f"Field size {field_size_mb:.2f} MB exceeds limit {self.config.max_field_size_mb} MB"
            )
            return self._process_large_field(field, operation, **kwargs)

        # Choose processing strategy
        if self.cuda_available and field_size_mb < 50.0:  # Use GPU for smaller fields
            try:
                result = self._process_gpu_optimized(field, operation, **kwargs)
                self.stats["gpu_usage"] += 1
            except Exception as e:
                self.logger.warning(f"GPU processing failed: {e}, falling back to CPU")
                self.stats["fallback_count"] += 1
                result = self._process_cpu_optimized(field, operation, **kwargs)
        else:
            result = self._process_cpu_optimized(field, operation, **kwargs)

        # Update statistics
        self.stats["processing_time"] += time.time() - start_time
        self.stats["blocks_processed"] += 1

        return result

    def _process_cpu_optimized(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """Process field using CPU with optimizations."""
        self.logger.info("Processing with CPU optimization")

        # Initialize result
        result = np.zeros_like(field, dtype=np.complex128)

        # Process in blocks
        for block_data, block_info in self.base_processor.iterate_blocks():
            # Process single block
            processed_block = self._process_single_block_cpu(
                block_data, operation, **kwargs
            )

            # Merge block result
            self._merge_block_result(result, processed_block, block_info)

            # Memory cleanup
            if self.config.enable_memory_optimization:
                gc.collect()

        return result

    def _process_gpu_optimized(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """Process field using GPU with optimizations."""
        if not self.cuda_available:
            raise RuntimeError("GPU processing requested but CUDA not available")

        self.logger.info("Processing with GPU optimization")

        # Transfer to GPU
        field_gpu = cp.asarray(field)
        result_gpu = cp.zeros_like(field_gpu, dtype=cp.complex128)

        try:
            # Process in blocks on GPU
            for block_data, block_info in self.base_processor.iterate_blocks():
                # Extract block on GPU
                block_gpu = self._extract_block_gpu(field_gpu, block_info)

                # Process block
                processed_block = self._process_single_block_gpu(
                    block_gpu, operation, **kwargs
                )

                # Merge result
                self._merge_block_result_gpu(result_gpu, processed_block, block_info)

            # Transfer back to CPU
            result = cp.asnumpy(result_gpu)

        finally:
            # Cleanup GPU memory
            del field_gpu, result_gpu
            cp.get_default_memory_pool().free_all_blocks()

        return result

    def _process_large_field(
        self, field: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """Process large field using minimal memory approach."""
        self.logger.info("Processing large field with minimal memory approach")

        # Use smaller blocks for large fields
        original_block_size = self.base_processor.block_size
        self.base_processor.block_size = max(2, self.block_size // 2)

        try:
            result = self._process_cpu_optimized(field, operation, **kwargs)
        finally:
            # Restore original block size
            self.base_processor.block_size = original_block_size

        return result

    def _process_single_block_cpu(
        self, block_data: np.ndarray, operation: str, **kwargs
    ) -> np.ndarray:
        """Process a single block on CPU."""
        if operation == "bvp_solve":
            return self._solve_bvp_block_cpu(block_data, **kwargs)
        elif operation == "fft":
            return np.fft.fftn(block_data)
        elif operation == "ifft":
            return np.fft.ifftn(block_data)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _process_single_block_gpu(self, block_data, operation: str, **kwargs):
        """Process a single block on GPU."""
        if operation == "bvp_solve":
            return self._solve_bvp_block_gpu(block_data, **kwargs)
        elif operation == "fft":
            return cp.fft.fftn(block_data)
        elif operation == "ifft":
            return cp.fft.ifftn(block_data)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _solve_bvp_block_cpu(self, block_data: np.ndarray, **kwargs) -> np.ndarray:
        """Solve BVP equation for a block on CPU."""
        # Simplified BVP solver for demonstration
        # In practice, this would implement the full BVP envelope equation
        return block_data * 0.5  # Placeholder implementation

    def _solve_bvp_block_gpu(self, block_data, **kwargs):
        """Solve BVP equation for a block on GPU."""
        # Simplified BVP solver for demonstration
        # In practice, this would implement the full BVP envelope equation
        return block_data * 0.5  # Placeholder implementation

    def _extract_block_gpu(self, field_gpu, block_info: BlockInfo):
        """Extract block from GPU field."""
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        return field_gpu[slices]

    def _merge_block_result(
        self, result: np.ndarray, block_result: np.ndarray, block_info: BlockInfo
    ) -> None:
        """Merge block result into main result array."""
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        result[slices] = block_result

    def _merge_block_result_gpu(
        self, result_gpu, block_result, block_info: BlockInfo
    ) -> None:
        """Merge block result into main result array on GPU."""
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        result_gpu[slices] = block_result

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
        Optimize processor settings for a specific field.

        Physical Meaning:
            Optimizes processor configuration based on field characteristics
            to maximize processing efficiency.
        """
        field_size_mb = field.nbytes / (1024**2)

        # Adjust block size based on field size
        if field_size_mb < 10:  # Small field
            self.base_processor.block_size = min(8, self.config.block_size)
        elif field_size_mb < 50:  # Medium field
            self.base_processor.block_size = min(4, self.config.block_size)
        else:  # Large field
            self.base_processor.block_size = max(2, self.config.block_size // 2)

        self.logger.info(
            f"Optimized block size for field: {self.base_processor.block_size}"
        )

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.cuda_available:
            cp.get_default_memory_pool().free_all_blocks()

        gc.collect()
        self.logger.info("Optimized block processor cleaned up")
