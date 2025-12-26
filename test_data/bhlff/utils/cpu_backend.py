"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU backend for computations when CUDA is not available.

This module provides the CPUBackend class for CPU-based operations on phase
fields. Note: Level C requires CUDA and will not use this backend.

Physical Meaning:
    Provides CPU-based array operations and FFT for phase field calculations
    using NumPy. This backend is provided for compatibility with other levels
    that may support CPU fallback.

WARNING:
    This backend is provided for compatibility with other levels.
    Level C code paths require CUDA and will raise RuntimeError
    if this backend is used.

Example:
    >>> from bhlff.utils.cpu_backend import CPUBackend
    >>> backend = CPUBackend()
    >>> array = backend.zeros((64, 64, 64))
"""

import logging
from typing import Optional
import numpy as np

# Try to import NumPy FFT
try:
    import numpy.fft as np_fft

    NUMPY_FFT_AVAILABLE = True
except ImportError:
    NUMPY_FFT_AVAILABLE = False
    np_fft = None

logger = logging.getLogger(__name__)


class CPUBackend:
    """
    CPU backend for computations when CUDA is not available.

    Physical Meaning:
        Provides CPU-based array operations and FFT for phase field
        calculations using NumPy. Note: Level C requires CUDA and will
        not use this backend.

    WARNING:
        This backend is provided for compatibility with other levels.
        Level C code paths require CUDA and will raise RuntimeError
        if this backend is used.
    """

    def __init__(self):
        """
        Initialize CPU backend.

        Physical Meaning:
            Sets up CPU-based computation backend for phase field calculations.

        Raises:
            RuntimeError: If NumPy FFT is not available.
        """
        if not NUMPY_FFT_AVAILABLE:
            raise RuntimeError("NumPy FFT not available")

        logger.info("CPU backend initialized")

    def zeros(self, shape: tuple, dtype=np.complex128) -> np.ndarray:
        """
        Create zero array on CPU.

        Physical Meaning:
            Allocates zero-initialized array on CPU for phase field
            computations with specified shape and dtype.

        Args:
            shape (tuple): Array shape.
            dtype: Data type (default: complex128 for phase fields).

        Returns:
            np.ndarray: Zero-initialized CPU array.
        """
        return np.zeros(shape, dtype=dtype)

    def ones(self, shape: tuple, dtype=np.complex128) -> np.ndarray:
        """
        Create ones array on CPU.

        Physical Meaning:
            Allocates ones-initialized array on CPU for phase field
            computations with specified shape and dtype.

        Args:
            shape (tuple): Array shape.
            dtype: Data type (default: complex128 for phase fields).

        Returns:
            np.ndarray: Ones-initialized CPU array.
        """
        return np.ones(shape, dtype=dtype)

    def array(self, array: np.ndarray) -> np.ndarray:
        """
        Return array as-is (already on CPU).

        Physical Meaning:
            Returns array without modification since it's already on CPU.

        Args:
            array (np.ndarray): Input array on CPU.

        Returns:
            np.ndarray: Same array (no transfer needed).
        """
        return array

    def to_numpy(self, array: np.ndarray) -> np.ndarray:
        """
        Return array as-is (already numpy).

        Physical Meaning:
            Returns array without modification since it's already NumPy array.

        Args:
            array (np.ndarray): Input array.

        Returns:
            np.ndarray: Same array (no conversion needed).
        """
        return array

    def fft(self, array: np.ndarray, axes: Optional[tuple] = None) -> np.ndarray:
        """
        Perform FFT on CPU.

        Physical Meaning:
            Computes multi-dimensional FFT using NumPy FFT implementation.

        Args:
            array (np.ndarray): Input array on CPU.
            axes (Optional[tuple]): Axes to transform (None = all axes).

        Returns:
            np.ndarray: FFT result on CPU.
        """
        return np_fft.fftn(array, axes=axes)

    def ifft(self, array: np.ndarray, axes: Optional[tuple] = None) -> np.ndarray:
        """
        Perform inverse FFT on CPU.

        Physical Meaning:
            Computes multi-dimensional inverse FFT using NumPy FFT implementation.

        Args:
            array (np.ndarray): Input array on CPU.
            axes (Optional[tuple]): Axes to transform (None = all axes).

        Returns:
            np.ndarray: IFFT result on CPU.
        """
        return np_fft.ifftn(array, axes=axes)

    def fftshift(self, array: np.ndarray, axes: Optional[tuple] = None) -> np.ndarray:
        """
        Perform FFT shift on CPU.

        Physical Meaning:
            Shifts zero-frequency component to center of spectrum.

        Args:
            array (np.ndarray): Input array on CPU.
            axes (Optional[tuple]): Axes to shift (None = all axes).

        Returns:
            np.ndarray: Shifted array on CPU.
        """
        return np_fft.fftshift(array, axes=axes)

    def ifftshift(self, array: np.ndarray, axes: Optional[tuple] = None) -> np.ndarray:
        """
        Perform inverse FFT shift on CPU.

        Physical Meaning:
            Inverse shift of zero-frequency component.

        Args:
            array (np.ndarray): Input array on CPU.
            axes (Optional[tuple]): Axes to shift (None = all axes).

        Returns:
            np.ndarray: Shifted array on CPU.
        """
        return np_fft.ifftshift(array, axes=axes)

    def get_memory_info(self) -> dict:
        """
        Get CPU memory information.

        Physical Meaning:
            Provides detailed information about CPU memory usage and
            availability for phase field computations.

        Returns:
            dict: CPU memory information including total, free, and used memory.
        """
        import psutil

        memory = psutil.virtual_memory()

        return {
            "total_memory": memory.total,
            "free_memory": memory.available,
            "used_memory": memory.used,
            "mempool_used": 0,
            "mempool_total": 0,
            "pinned_used": 0,
            "pinned_total": 0,
        }
