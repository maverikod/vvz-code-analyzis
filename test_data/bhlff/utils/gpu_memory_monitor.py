"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU memory monitoring utilities for BHLFF project.

This module provides specialized GPU memory monitoring functionality
with automatic warnings and memory pool management.

Physical Meaning:
    Monitors GPU memory usage during phase field computations to ensure
    efficient resource utilization and prevent memory overflow with
    automatic warnings and memory pool management.

Mathematical Foundation:
    Tracks GPU memory allocation patterns and provides optimization
    recommendations for large-scale 7D computations on GPU.

Example:
    >>> monitor = GPUMemoryMonitor(warning_threshold=0.75, critical_threshold=0.9)
    >>> memory_info = monitor.check_memory()
    >>> if memory_info['usage_ratio'] > 0.9:
    ...     raise MemoryError("GPU memory critical")
"""

import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class GPUMemoryMonitor:
    """
    GPU memory monitor with automatic warnings and memory pool management.
    
    Physical Meaning:
        Monitors GPU memory usage during phase field computations,
        providing automatic warnings and memory pool management to
        prevent memory overflow and optimize GPU utilization.
        
    Mathematical Foundation:
        Tracks GPU memory usage ratio and provides recommendations
        for optimal memory management in 7D phase field computations.
        
    Attributes:
        warning_threshold (float): Warning threshold for memory usage ratio.
        critical_threshold (float): Critical threshold for memory usage ratio.
        cuda_available (bool): Whether CUDA is available.
    """
    
    def __init__(
        self,
        warning_threshold: float = 0.75,
        critical_threshold: float = 0.9,
    ):
        """
        Initialize GPU memory monitor.
        
        Physical Meaning:
            Sets up GPU memory monitoring with specified thresholds
            for warnings and critical alerts.
            
        Args:
            warning_threshold (float): Warning threshold for memory usage ratio
                (default: 0.75 for 75% usage).
            critical_threshold (float): Critical threshold for memory usage ratio
                (default: 0.9 for 90% usage).
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.cuda_available = CUDA_AVAILABLE
        
        if not self.cuda_available:
            logger.warning(
                "CUDA not available - GPUMemoryMonitor will not function properly"
            )
    
    def check_memory(self) -> Dict[str, Any]:
        """
        Check GPU memory usage and raise warnings if thresholds exceeded.
        
        Physical Meaning:
            Checks current GPU memory usage and provides warnings
            or raises exceptions if thresholds are exceeded.
            
        Returns:
            Dict[str, Any]: GPU memory information including:
                - free: Free GPU memory in bytes
                - total: Total GPU memory in bytes
                - used: Used GPU memory in bytes
                - usage_ratio: Memory usage ratio (0.0 to 1.0)
                
        Raises:
            MemoryError: If memory usage exceeds critical threshold.
            RuntimeError: If CUDA is not available.
        """
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - cannot check GPU memory")
        
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free = mem_info[0]
            total = mem_info[1]
            used = total - free
            usage_ratio = used / total if total > 0 else 0.0
            
            result = {
                "free": free,
                "total": total,
                "used": used,
                "usage_ratio": usage_ratio,
            }
            
            # Check thresholds and log warnings
            if usage_ratio > self.critical_threshold:
                error_msg = (
                    f"GPU memory critical: {usage_ratio:.1%} used "
                    f"(threshold: {self.critical_threshold:.1%})"
                )
                logger.error(error_msg)
                raise MemoryError(error_msg)
            elif usage_ratio > self.warning_threshold:
                logger.warning(
                    f"GPU memory high: {usage_ratio:.1%} used "
                    f"(threshold: {self.warning_threshold:.1%})"
                )
            
            return result
        except Exception as e:
            logger.error(f"Failed to check GPU memory: {e}")
            raise RuntimeError(f"Failed to check GPU memory: {e}") from e
    
    def get_memory_pool_info(self) -> Dict[str, Any]:
        """
        Get GPU memory pool information.
        
        Physical Meaning:
            Returns information about GPU memory pools for monitoring
            and optimization of memory allocation patterns.
            
        Returns:
            Dict[str, Any]: Memory pool information including:
                - mempool_used: Used memory pool bytes
                - mempool_total: Total memory pool bytes
                - pinned_used: Used pinned memory pool bytes
                - pinned_total: Total pinned memory pool bytes
        """
        if not self.cuda_available:
            return {"error": "CUDA not available"}
        
        try:
            mempool = cp.get_default_memory_pool()
            pinned_mempool = cp.get_default_pinned_memory_pool()
            
            return {
                "mempool_used": mempool.used_bytes(),
                "mempool_total": mempool.total_bytes(),
                "pinned_used": pinned_mempool.used_bytes(),
                "pinned_total": pinned_mempool.total_bytes(),
            }
        except Exception as e:
            logger.error(f"Failed to get memory pool info: {e}")
            return {"error": str(e)}
    
    def free_all_blocks(self) -> None:
        """
        Free all blocks in GPU memory pools.
        
        Physical Meaning:
            Forces freeing of all blocks in GPU memory pools,
            useful for memory cleanup and defragmentation.
        """
        if not self.cuda_available:
            logger.warning("CUDA not available - cannot free GPU memory blocks")
            return
        
        try:
            mempool = cp.get_default_memory_pool()
            pinned_mempool = cp.get_default_pinned_memory_pool()
            
            mempool.free_all_blocks()
            pinned_mempool.free_all_blocks()
            
            logger.info("Freed all GPU memory pool blocks")
        except Exception as e:
            logger.error(f"Failed to free GPU memory blocks: {e}")
    
    def get_available_memory(self, memory_ratio: float = 0.8) -> int:
        """
        Get available GPU memory for block processing.
        
        Physical Meaning:
            Calculates available GPU memory for block processing
            based on specified memory ratio (default: 80%).
            
        Args:
            memory_ratio (float): Fraction of free memory to use
                (default: 0.8 for 80% usage).
                
        Returns:
            int: Available memory in bytes for block processing.
        """
        if not self.cuda_available:
            return 0
        
        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free = mem_info[0]
            return int(free * memory_ratio)
        except Exception as e:
            logger.error(f"Failed to get available GPU memory: {e}")
            return 0


@contextmanager
def gpu_memory_context(max_usage_ratio: float = 0.8):
    """
    Context manager for automatic GPU memory management.
    
    Physical Meaning:
        Provides automatic GPU memory management with cleanup
        on exit, ensuring efficient memory usage during computations.
        
    Args:
        max_usage_ratio (float): Maximum memory usage ratio
            (default: 0.8 for 80% usage).
            
    Example:
        >>> with gpu_memory_context(max_usage_ratio=0.8):
        ...     # GPU operations here
        ...     result = compute_on_gpu(data)
    """
    monitor = GPUMemoryMonitor(
        warning_threshold=max_usage_ratio * 0.9,
        critical_threshold=max_usage_ratio * 1.1,
    )
    
    try:
        # Check memory before operations
        monitor.check_memory()
        yield monitor
    finally:
        # Cleanup memory pools
        monitor.free_all_blocks()
        logger.debug("GPU memory context cleanup completed")

