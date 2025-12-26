"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA helper methods for phase components.
"""

import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class PhaseComponentsCUDAHelpers:
    """
    CUDA helper methods for phase components.

    Physical Meaning:
        Provides CUDA-accelerated operations for phase component
        computations, enabling efficient GPU-based processing.
    """

    def __init__(self, use_cuda: bool):
        """
        Initialize CUDA helpers.

        Args:
            use_cuda (bool): Whether to use CUDA.
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE

    def to_gpu(self, array: np.ndarray):
        """
        Convert numpy array to GPU array.

        Physical Meaning:
            Transfers array to GPU memory for CUDA computation.

        Args:
            array (np.ndarray): Input array.

        Returns:
            GPU array or original array if CUDA not available.
        """
        if self.use_cuda:
            return cp.asarray(array)
        return array

    def to_cpu(self, array) -> np.ndarray:
        """
        Convert GPU array to numpy array.

        Physical Meaning:
            Transfers array from GPU memory to CPU memory.

        Args:
            array: Input array (GPU or CPU).

        Returns:
            np.ndarray: CPU array.
        """
        if self.use_cuda and hasattr(array, "get"):
            return array.get()
        return array

    def cuda_exp(self, array):
        """
        Compute exponential using CUDA.

        Physical Meaning:
            Computes exponential using CUDA for optimal performance.

        Args:
            array: Input array.

        Returns:
            Exponential array.
        """
        if self.use_cuda:
            return cp.exp(array)
        return np.exp(array)

    def cuda_abs(self, array):
        """
        Compute absolute value using CUDA.

        Physical Meaning:
            Computes absolute value using CUDA for optimal performance.

        Args:
            array: Input array.

        Returns:
            Absolute value array.
        """
        if self.use_cuda:
            return cp.abs(array)
        return np.abs(array)

    def cuda_angle(self, array):
        """
        Compute angle using CUDA.

        Physical Meaning:
            Computes angle using CUDA for optimal performance.

        Args:
            array: Input array.

        Returns:
            Angle array.
        """
        if self.use_cuda:
            return cp.angle(array)
        return np.angle(array)

    def cuda_mean(self, array, axis=None):
        """
        Compute mean using CUDA.

        Physical Meaning:
            Computes mean using CUDA for optimal performance.

        Args:
            array: Input array.
            axis: Axis along which to compute mean.

        Returns:
            Mean array.
        """
        if self.use_cuda:
            return cp.mean(array, axis=axis)
        return np.mean(array, axis=axis)

