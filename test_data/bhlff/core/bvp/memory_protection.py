"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory protection module for BVP calculations.

This module implements memory protection mechanisms to prevent
out-of-memory errors during large-scale 7D BVP calculations.

Physical Meaning:
    Monitors memory usage during BVP calculations to ensure
    computational resources are used efficiently and prevent
    system crashes due to excessive memory consumption.

Mathematical Foundation:
    Estimates memory requirements based on domain size and
    data types, providing early warning when memory usage
    approaches system limits.

Example:
    >>> protector = MemoryProtector()
    >>> protector.check_memory_usage(domain_shape, data_type)
"""

import psutil
import numpy as np
from typing import Tuple, Optional
import warnings


class MemoryProtector:
    """
    Memory protection for BVP calculations.

    Physical Meaning:
        Monitors memory usage during BVP calculations to ensure
        computational resources are used efficiently and prevent
        system crashes due to excessive memory consumption.

    Mathematical Foundation:
        Estimates memory requirements based on domain size and
        data types, providing early warning when memory usage
        approaches system limits.
    """

    def __init__(self, memory_threshold: float = 0.8):
        """
        Initialize memory protector.

        Physical Meaning:
            Sets up memory protection with configurable threshold
            to prevent out-of-memory errors during calculations.

        Args:
            memory_threshold (float): Memory usage threshold (0.0-1.0).
                Default 0.8 means 80% of available memory.
        """
        self.memory_threshold = memory_threshold
        self.total_memory = psutil.virtual_memory().total
        self.available_memory = psutil.virtual_memory().available

    def check_memory_usage(
        self, domain_shape: Tuple[int, ...], data_type: np.dtype = np.float64
    ) -> bool:
        """
        Check if memory usage would exceed threshold.

        Physical Meaning:
            Estimates memory requirements for the given domain
            and data type, checking against the memory threshold.

        Mathematical Foundation:
            Memory estimate = domain_size * data_type_size * safety_factor
            where safety_factor accounts for intermediate calculations.

        Args:
            domain_shape (Tuple[int, ...]): Shape of the computational domain.
            data_type (np.dtype): Data type for calculations.

        Returns:
            bool: True if memory usage is safe, False if threshold would be exceeded.

        Raises:
            MemoryError: If memory usage would exceed threshold.
        """
        # Calculate domain size
        domain_size = np.prod(domain_shape)

        # Calculate data type size
        if data_type == np.float64:
            dtype_size = 8  # bytes
        elif data_type == np.float32:
            dtype_size = 4  # bytes
        elif data_type == np.complex128:
            dtype_size = 16  # bytes
        elif data_type == np.complex64:
            dtype_size = 8  # bytes
        else:
            dtype_size = 8  # default to float64 size

        # Estimate memory requirement with safety factor
        # Safety factor accounts for intermediate calculations, gradients, etc.
        safety_factor = 10.0  # Conservative estimate for 7D calculations
        estimated_memory = domain_size * dtype_size * safety_factor

        # Get current memory usage
        current_memory = psutil.virtual_memory().used
        available_memory = psutil.virtual_memory().available

        # Calculate projected memory usage
        projected_memory = current_memory + estimated_memory
        memory_usage_ratio = projected_memory / self.total_memory

        # Check against threshold
        if memory_usage_ratio > self.memory_threshold:
            error_msg = (
                f"Memory usage would exceed {self.memory_threshold*100:.1f}% threshold. "
                f"Projected usage: {memory_usage_ratio*100:.1f}% "
                f"(estimated {estimated_memory/1024**3:.2f} GB). "
                f"Domain shape: {domain_shape}, data type: {data_type}. "
                f"Consider reducing domain size or using lower precision."
            )
            raise MemoryError(error_msg)

        return True

    def get_memory_info(self) -> dict:
        """
        Get current memory information.

        Physical Meaning:
            Returns current memory usage statistics for monitoring
            and debugging purposes.

        Returns:
            dict: Memory information including:
                - total_memory: Total system memory in bytes
                - used_memory: Currently used memory in bytes
                - available_memory: Available memory in bytes
                - memory_percent: Memory usage percentage
                - threshold: Memory threshold setting
        """
        memory = psutil.virtual_memory()
        return {
            "total_memory": memory.total,
            "used_memory": memory.used,
            "available_memory": memory.available,
            "memory_percent": memory.percent,
            "threshold": self.memory_threshold,
            "threshold_bytes": int(self.total_memory * self.memory_threshold),
        }

    def estimate_memory_requirement(
        self, domain_shape: Tuple[int, ...], data_type: np.dtype = np.float64
    ) -> dict:
        """
        Estimate memory requirement for given domain and data type.

        Physical Meaning:
            Calculates estimated memory requirements for BVP calculations
            with the given domain size and data type.

        Mathematical Foundation:
            Memory estimate = domain_size * data_type_size * safety_factor
            where safety_factor accounts for intermediate calculations.

        Args:
            domain_shape (Tuple[int, ...]): Shape of the computational domain.
            data_type (np.dtype): Data type for calculations.

        Returns:
            dict: Memory requirement information including:
                - estimated_memory: Estimated memory requirement in bytes
                - estimated_memory_gb: Estimated memory requirement in GB
                - domain_size: Total number of elements
                - data_type_size: Size of each element in bytes
                - safety_factor: Safety factor used in calculation
        """
        # Calculate domain size
        domain_size = np.prod(domain_shape)

        # Calculate data type size
        if data_type == np.float64:
            dtype_size = 8  # bytes
        elif data_type == np.float32:
            dtype_size = 4  # bytes
        elif data_type == np.complex128:
            dtype_size = 16  # bytes
        elif data_type == np.complex64:
            dtype_size = 8  # bytes
        else:
            dtype_size = 8  # default to float64 size

        # Estimate memory requirement with safety factor
        safety_factor = 10.0  # Conservative estimate for 7D calculations
        estimated_memory = domain_size * dtype_size * safety_factor

        return {
            "estimated_memory": estimated_memory,
            "estimated_memory_gb": estimated_memory / (1024**3),
            "domain_size": domain_size,
            "data_type_size": dtype_size,
            "safety_factor": safety_factor,
        }

    def check_and_warn(
        self, domain_shape: Tuple[int, ...], data_type: np.dtype = np.float64
    ) -> bool:
        """
        Check memory usage and issue warning if approaching threshold.

        Physical Meaning:
            Checks memory usage and issues a warning if it approaches
            the threshold, allowing for graceful handling.

        Args:
            domain_shape (Tuple[int, ...]): Shape of the computational domain.
            data_type (np.dtype): Data type for calculations.

        Returns:
            bool: True if memory usage is safe, False if approaching threshold.
        """
        try:
            self.check_memory_usage(domain_shape, data_type)
            return True
        except MemoryError as e:
            warnings.warn(str(e), UserWarning)
            return False
