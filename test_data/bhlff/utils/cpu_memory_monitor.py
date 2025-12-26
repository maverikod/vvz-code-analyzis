"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU memory monitoring utilities for BHLFF project.

This module provides specialized CPU memory monitoring functionality
with automatic warnings and memory-mapped array support.

Physical Meaning:
    Monitors CPU memory usage during phase field computations to ensure
    efficient resource utilization and prevent memory overflow with
    automatic warnings and memory-mapped array support.

Mathematical Foundation:
    Tracks CPU memory allocation patterns and provides optimization
    recommendations for large-scale 7D computations on CPU.

Example:
    >>> monitor = CPUMemoryMonitor(warning_threshold=0.75, critical_threshold=0.9)
    >>> if monitor.check_memory(required_bytes=1024**3):
    ...     array = create_large_array(shape, dtype)
"""

import logging
import psutil
from typing import Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class CPUMemoryMonitor:
    """
    CPU memory monitor with automatic warnings and memory-mapped array support.
    
    Physical Meaning:
        Monitors CPU memory usage during phase field computations,
        providing automatic warnings and support for memory-mapped
        arrays for large datasets.
        
    Mathematical Foundation:
        Tracks CPU memory usage ratio and provides recommendations
        for optimal memory management in 7D phase field computations.
        
    Attributes:
        warning_threshold (float): Warning threshold for memory usage ratio.
        critical_threshold (float): Critical threshold for memory usage ratio.
    """
    
    def __init__(
        self,
        warning_threshold: float = 0.75,
        critical_threshold: float = 0.9,
    ):
        """
        Initialize CPU memory monitor.
        
        Physical Meaning:
            Sets up CPU memory monitoring with specified thresholds
            for warnings and critical alerts.
            
        Args:
            warning_threshold (float): Warning threshold for memory usage ratio
                (default: 0.75 for 75% usage).
            critical_threshold (float): Critical threshold for memory usage ratio
                (default: 0.9 for 90% usage).
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    def check_memory(self, required_bytes: Optional[int] = None) -> Dict[str, Any]:
        """
        Check CPU memory usage and verify if required memory is available.
        
        Physical Meaning:
            Checks current CPU memory usage and verifies if specified
            amount of memory is available for allocation.
            
        Args:
            required_bytes (Optional[int]): Required memory in bytes
                (if None, only checks current usage).
                
        Returns:
            Dict[str, Any]: CPU memory information including:
                - total: Total CPU memory in bytes
                - available: Available CPU memory in bytes
                - used: Used CPU memory in bytes
                - usage_ratio: Memory usage ratio (0.0 to 1.0)
                - sufficient: Whether required memory is available (if specified)
                
        Raises:
            MemoryError: If required memory is not available.
        """
        try:
            memory = psutil.virtual_memory()
            total = memory.total
            available = memory.available
            used = memory.used
            usage_ratio = memory.percent / 100.0
            
            result = {
                "total": total,
                "available": available,
                "used": used,
                "usage_ratio": usage_ratio,
            }
            
            # Check if required memory is available
            if required_bytes is not None:
                # Use 80% of available memory as limit (project requirement)
                available_limit = available * 0.8
                sufficient = required_bytes <= available_limit
                result["required_bytes"] = required_bytes
                result["available_limit"] = available_limit
                result["sufficient"] = sufficient
                
                if not sufficient:
                    error_msg = (
                        f"Insufficient CPU memory: required {required_bytes / (1024**3):.2f} GB, "
                        f"available {available_limit / (1024**3):.2f} GB "
                        f"(80% of {available / (1024**3):.2f} GB free)"
                    )
                    logger.error(error_msg)
                    raise MemoryError(error_msg)
            
            # Check thresholds and log warnings
            if usage_ratio > self.critical_threshold:
                logger.error(
                    f"CPU memory critical: {usage_ratio:.1%} used "
                    f"(threshold: {self.critical_threshold:.1%})"
                )
            elif usage_ratio > self.warning_threshold:
                logger.warning(
                    f"CPU memory high: {usage_ratio:.1%} used "
                    f"(threshold: {self.warning_threshold:.1%})"
                )
            
            return result
        except Exception as e:
            logger.error(f"Failed to check CPU memory: {e}")
            raise RuntimeError(f"Failed to check CPU memory: {e}") from e
    
    def should_use_memory_mapped(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype = np.complex128,
        threshold_gb: float = 10.0,
    ) -> bool:
        """
        Determine if memory-mapped array should be used.
        
        Physical Meaning:
            Determines if array should use memory-mapped storage
            based on size and available memory.
            
        Args:
            shape (Tuple[int, ...]): Array shape.
            dtype (np.dtype): Data type (default: complex128).
            threshold_gb (float): Threshold in GB for using memory mapping
                (default: 10.0 GB).
                
        Returns:
            bool: True if memory-mapped array should be used.
        """
        try:
            array_size_bytes = np.prod(shape) * np.dtype(dtype).itemsize
            array_size_gb = array_size_bytes / (1024**3)
            
            return array_size_gb > threshold_gb
        except Exception as e:
            logger.error(f"Failed to determine memory-mapped usage: {e}")
            return False
    
    def get_available_memory(self, memory_ratio: float = 0.8) -> int:
        """
        Get available CPU memory for block processing.
        
        Physical Meaning:
            Calculates available CPU memory for block processing
            based on specified memory ratio (default: 80%).
            
        Args:
            memory_ratio (float): Fraction of available memory to use
                (default: 0.8 for 80% usage).
                
        Returns:
            int: Available memory in bytes for block processing.
        """
        try:
            memory = psutil.virtual_memory()
            available = memory.available
            return int(available * memory_ratio)
        except Exception as e:
            logger.error(f"Failed to get available CPU memory: {e}")
            return 0

