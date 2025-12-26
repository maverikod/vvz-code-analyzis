"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU block processing utilities for 7D fields.

This module implements utility functions for GPU block processing
including memory pressure checking, block extraction, and merging.
"""

import logging
import gc
import numpy as np
from typing import Union, Any

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..block_processor import BlockInfo
from ....utils.gpu_memory_monitor import GPUMemoryMonitor


class GPUBlockUtils:
    """
    GPU block processing utilities.

    Physical Meaning:
        Provides utility functions for GPU block processing including
        memory pressure checking, block extraction, and merging operations
        for 7D phase fields.

    Mathematical Foundation:
        Implements utilities for 7D block processing with 80% GPU memory
        limit for optimal performance.
    """

    def __init__(self, cuda_available: bool, logger: logging.Logger = None):
        """
        Initialize GPU block utilities.

        Args:
            cuda_available (bool): Whether CUDA is available.
            logger (logging.Logger): Logger instance.
        """
        self.cuda_available = cuda_available and CUDA_AVAILABLE
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize GPU memory monitor
        self._gpu_memory_monitor = GPUMemoryMonitor(
            warning_threshold=0.75,
            critical_threshold=0.9,
        ) if self.cuda_available else None

    def extract_block_gpu(
        self, field_gpu: Union[np.ndarray, Any], block_info: BlockInfo
    ) -> Union[np.ndarray, Any]:
        """
        Extract block from GPU field.

        Physical Meaning:
            Extracts a 7D block from GPU field using vectorized slicing
            operations for optimal performance.

        Args:
            field_gpu (Union[np.ndarray, Any]): GPU field array.
            block_info (BlockInfo): Block information.

        Returns:
            Union[np.ndarray, Any]: Extracted block on GPU.
        """
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        return field_gpu[slices]

    def merge_block_result_gpu(
        self,
        result_gpu: Union[np.ndarray, Any],
        block_result: Union[np.ndarray, Any],
        block_info: BlockInfo,
    ) -> None:
        """
        Merge block result into main result array on GPU.

        Physical Meaning:
            Merges processed 7D block result into main result array
            on GPU using vectorized operations.

        Args:
            result_gpu (Union[np.ndarray, Any]): Main result array on GPU.
            block_result (Union[np.ndarray, Any]): Processed block result.
            block_info (BlockInfo): Block information.
        """
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        result_gpu[slices] = block_result

    def check_gpu_memory_pressure(
        self, use_7d_operations: bool = False
    ) -> None:
        """
        Check GPU memory pressure and apply backpressure if needed.

        Physical Meaning:
            Monitors GPU memory usage and applies backpressure by
            synchronizing streams and freeing unused memory blocks
            to prevent OOM errors. For 7D operations, uses stricter
            thresholds (80% rule) to maintain optimal performance.

        Args:
            use_7d_operations (bool): If True, uses stricter thresholds
                for 7D operations (80% memory limit).

        Raises:
            RuntimeError: If GPU memory is critically low.
        """
        if not self.cuda_available or self._gpu_memory_monitor is None:
            return

        try:
            # Use GPUMemoryMonitor for consistent memory checking
            gpu_mem_info = self._gpu_memory_monitor.check_memory()
            usage_ratio = gpu_mem_info["usage_ratio"]

            # For 7D operations, enforce 80% GPU memory limit (project requirement)
            # For other operations, use 90% threshold
            threshold = 0.8 if use_7d_operations else 0.9

            # If memory usage exceeds threshold, apply backpressure
            if usage_ratio > threshold:
                self.logger.warning(
                    f"High GPU memory usage: {usage_ratio*100:.1f}% "
                    f"(threshold: {threshold*100:.0f}%), applying backpressure. "
                    f"Free: {gpu_mem_info['free'] / (1024**3):.2f} GB, "
                    f"Total: {gpu_mem_info['total'] / (1024**3):.2f} GB"
                )
                # Free memory pools and synchronize
                self._gpu_memory_monitor.free_all_blocks()
                if CUDA_AVAILABLE:
                    cp.cuda.Stream.null.synchronize()
                gc.collect()

                # For 7D operations, if still over limit, raise error
                if use_7d_operations and usage_ratio > 0.85:
                    raise RuntimeError(
                        f"GPU memory usage {usage_ratio*100:.1f}% exceeds "
                        f"80% limit for 7D operations. Please reduce block size "
                        f"or field dimensions."
                    )

        except MemoryError as e:
            # GPUMemoryMonitor raised MemoryError for critical usage
            self.logger.error(f"GPU memory critical: {e}")
            raise RuntimeError(
                f"GPU memory critical for 7D operations: {e}"
            ) from e
        except Exception as e:
            self.logger.warning(f"Failed to check GPU memory pressure: {e}")
            raise

