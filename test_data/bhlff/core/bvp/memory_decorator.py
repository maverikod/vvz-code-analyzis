"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory protection decorator for BVP calculations.

This module provides a universal decorator for memory protection
that can be applied to any BVP calculation method to prevent
out-of-memory errors.

Physical Meaning:
    Provides automatic memory protection for all BVP calculations
    by monitoring memory usage and preventing calculations that
    would exceed system memory limits.

Mathematical Foundation:
    Estimates memory requirements based on input parameters
    and applies memory protection before executing calculations.

Example:
    >>> @memory_protected
    >>> def solve_equation(domain_shape, data_type):
    >>>     # Calculation code here
    >>>     pass
"""

import functools
import numpy as np
from typing import Callable, Any, Tuple, Optional
from .memory_protection import MemoryProtector


def memory_protected(
    memory_threshold: float = 0.8,
    shape_param: str = "shape",
    dtype_param: str = "dtype",
):
    """
    Decorator for automatic memory protection.

    Physical Meaning:
        Automatically checks memory usage before executing
        BVP calculations and prevents out-of-memory errors.

    Mathematical Foundation:
        Estimates memory requirements from input parameters
        and applies memory protection with configurable threshold.

    Args:
        memory_threshold (float): Memory usage threshold (0.0-1.0).
        shape_param (str): Parameter name containing shape information.
        dtype_param (str): Parameter name containing data type information.

    Returns:
        Callable: Decorated function with memory protection.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Initialize memory protector
            protector = MemoryProtector(memory_threshold)

            # Extract shape and dtype from parameters
            shape = None
            dtype = np.float64  # default

            # Try to get shape from kwargs
            if shape_param in kwargs:
                shape = kwargs[shape_param]
            elif len(args) > 0:
                # Try to get shape from first argument
                if hasattr(args[0], "shape"):
                    shape = args[0].shape
                elif isinstance(args[0], (tuple, list)):
                    shape = args[0]

            # Try to get dtype from kwargs
            if dtype_param in kwargs:
                dtype = kwargs[dtype_param]
            elif len(args) > 1:
                # Try to get dtype from second argument
                if hasattr(args[1], "dtype"):
                    dtype = args[1].dtype
                elif isinstance(args[1], type):
                    dtype = args[1]

            # Check memory usage if shape is available
            if shape is not None:
                try:
                    protector.check_memory_usage(shape, dtype)
                except MemoryError as e:
                    raise MemoryError(
                        f"Memory protection triggered in {func.__name__}: {e}. "
                        f"Consider reducing domain size or using lower precision."
                    )

            # Execute the function
            return func(*args, **kwargs)

        return wrapper

    return decorator


def memory_protected_method(
    memory_threshold: float = 0.8,
    shape_param: str = "shape",
    dtype_param: str = "dtype",
):
    """
    Decorator for automatic memory protection on class methods.

    Physical Meaning:
        Automatically checks memory usage before executing
        BVP calculation methods and prevents out-of-memory errors.

    Args:
        memory_threshold (float): Memory usage threshold (0.0-1.0).
        shape_param (str): Parameter name containing shape information.
        dtype_param (str): Parameter name containing data type information.

    Returns:
        Callable: Decorated method with memory protection.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Initialize memory protector
            protector = MemoryProtector(memory_threshold)

            # Extract shape and dtype from parameters
            shape = None
            dtype = np.float64  # default

            # Try to get shape from kwargs
            if shape_param in kwargs:
                shape = kwargs[shape_param]
            elif len(args) > 0:
                # Try to get shape from first argument
                if hasattr(args[0], "shape"):
                    shape = args[0].shape
                elif isinstance(args[0], (tuple, list)):
                    shape = args[0]

            # Try to get dtype from kwargs
            if dtype_param in kwargs:
                dtype = kwargs[dtype_param]
            elif len(args) > 1:
                # Try to get dtype from second argument
                if hasattr(args[1], "dtype"):
                    dtype = args[1].dtype
                elif isinstance(args[1], type):
                    dtype = args[1]

            # Check memory usage if shape is available
            if shape is not None:
                try:
                    protector.check_memory_usage(shape, dtype)
                except MemoryError as e:
                    raise MemoryError(
                        f"Memory protection triggered in {func.__name__}: {e}. "
                        f"Consider reducing domain size or using lower precision."
                    )

            # Execute the method
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def memory_protected_class_method(
    memory_threshold: float = 0.8,
    shape_param: str = "shape",
    dtype_param: str = "dtype",
):
    """
    Decorator for automatic memory protection on class methods with self access.

    Physical Meaning:
        Automatically checks memory usage before executing
        BVP calculation methods, using class-level memory protection
        if available.

    Args:
        memory_threshold (float): Memory usage threshold (0.0-1.0).
        shape_param (str): Parameter name containing shape information.
        dtype_param (str): Parameter name containing data type information.

    Returns:
        Callable: Decorated method with memory protection.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Use class memory protector if available, otherwise create new one
            if hasattr(self, "memory_protector"):
                protector = self.memory_protector
            else:
                protector = MemoryProtector(memory_threshold)

            # Extract shape and dtype from parameters
            shape = None
            dtype = np.float64  # default

            # Try to get shape from kwargs
            if shape_param in kwargs:
                shape = kwargs[shape_param]
            elif len(args) > 0:
                # Try to get shape from first argument
                if hasattr(args[0], "shape"):
                    shape = args[0].shape
                elif isinstance(args[0], (tuple, list)):
                    shape = args[0]

            # Try to get dtype from kwargs
            if dtype_param in kwargs:
                dtype = kwargs[dtype_param]
            elif len(args) > 1:
                # Try to get dtype from second argument
                if hasattr(args[1], "dtype"):
                    dtype = args[1].dtype
                elif isinstance(args[1], type):
                    dtype = args[1]

            # Check memory usage if shape is available
            # For methods that support block processing (like solve_envelope),
            # allow them to proceed - they will automatically use block processing
            if shape is not None:
                try:
                    protector.check_memory_usage(shape, dtype)
                except MemoryError as e:
                    # Check if method supports block processing
                    # Methods that handle BlockedField or have _block_processor
                    # should be allowed to proceed - they'll use blocks automatically
                    supports_block_processing = (
                        hasattr(self, '_block_processor') or
                        hasattr(self, 'solve_envelope_blocked') or
                        func.__name__ == 'solve_envelope'  # This method handles blocks
                    )
                    
                    if supports_block_processing:
                        # Method supports block processing - let it handle memory
                        # It will automatically use blocks for large domains
                        pass
                    else:
                        # No block processing available - raise error
                        raise MemoryError(
                            f"Memory protection triggered in {func.__name__}: {e}. "
                            f"Consider reducing domain size or using lower precision."
                        )

            # Execute the method
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def memory_protected_function(
    memory_threshold: float = 0.8,
    shape_param: str = "shape",
    dtype_param: str = "dtype",
):
    """
    Decorator for automatic memory protection on standalone functions.

    Physical Meaning:
        Automatically checks memory usage before executing
        BVP calculation functions and prevents out-of-memory errors.

    Args:
        memory_threshold (float): Memory usage threshold (0.0-1.0).
        shape_param (str): Parameter name containing shape information.
        dtype_param (str): Parameter name containing data type information.

    Returns:
        Callable: Decorated function with memory protection.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Initialize memory protector
            protector = MemoryProtector(memory_threshold)

            # Extract shape and dtype from parameters
            shape = None
            dtype = np.float64  # default

            # Try to get shape from kwargs
            if shape_param in kwargs:
                shape = kwargs[shape_param]
            elif len(args) > 0:
                # Try to get shape from first argument
                if hasattr(args[0], "shape"):
                    shape = args[0].shape
                elif isinstance(args[0], (tuple, list)):
                    shape = args[0]

            # Try to get dtype from kwargs
            if dtype_param in kwargs:
                dtype = kwargs[dtype_param]
            elif len(args) > 1:
                # Try to get dtype from second argument
                if hasattr(args[1], "dtype"):
                    dtype = args[1].dtype
                elif isinstance(args[1], type):
                    dtype = args[1]

            # Check memory usage if shape is available
            if shape is not None:
                try:
                    protector.check_memory_usage(shape, dtype)
                except MemoryError as e:
                    raise MemoryError(
                        f"Memory protection triggered in {func.__name__}: {e}. "
                        f"Consider reducing domain size or using lower precision."
                    )

            # Execute the function
            return func(*args, **kwargs)

        return wrapper

    return decorator
