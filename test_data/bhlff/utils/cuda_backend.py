"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA backend for GPU-accelerated computations with 7D support.

This module provides the CUDABackend class for GPU-accelerated operations
on 7D phase fields with block-based processing and vectorized operations.

Physical Meaning:
    CUDA backend provides GPU-accelerated array operations, FFT, and 7D-specific
    operations (Laplacian, spectral operations) for 7D phase field calculations
    in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ using CuPy with optimal block processing.

Theoretical Background:
    The 7D phase field theory operates in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where:
    - Spatial coordinates: x ∈ ℝ³ (dimensions 0, 1, 2)
    - Phase coordinates: φ ∈ 𝕋³ (dimensions 3, 4, 5)
    - Time: t ∈ ℝ (dimension 6)
    All operations preserve 7D structure and use vectorized GPU kernels.

Example:
    >>> from bhlff.utils.cuda_backend import CUDABackend
    >>> backend = CUDABackend()
    >>> array = backend.zeros((64, 64, 64, 16, 16, 16, 100))
    >>> laplacian = backend.laplacian_7d(array, h=1.0)
"""

import logging
from typing import Optional
import numpy as np

# Try to import CUDA libraries
try:
    import cupy as cp
    import cupyx.scipy.fft as cp_fft

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None
    cp_fft = None

from .cuda_backend_7d_ops import CUDABackend7DOps

logger = logging.getLogger(__name__)


class CUDABackend(CUDABackend7DOps):
    """
    CUDA backend for GPU-accelerated computations with 7D support.

    Physical Meaning:
        Provides GPU-accelerated array operations, FFT, and 7D-specific
        operations (Laplacian, spectral operations) for 7D phase field
        calculations using CuPy with vectorized operations and optimal
        block processing.

    Mathematical Foundation:
        Implements 7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - 7D FFT: operations on all 7 dimensions
        - Block processing: optimized for 80% GPU memory usage

    Attributes:
        device (cp.cuda.Device): CUDA device instance.
        memory_pool: Default memory pool for GPU allocations.
        pinned_memory_pool: Pinned memory pool for efficient transfers.
    """

    def __init__(self):
        """
        Initialize CUDA backend.

        Physical Meaning:
            Sets up GPU-accelerated computation backend with memory pools
            and device management for 7D phase field calculations.

        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA not available. Level C requires GPU acceleration. "
                "Please install CuPy and ensure CUDA is properly configured."
            )

        self.device = cp.cuda.Device()
        self.memory_pool = cp.get_default_memory_pool()
        self.pinned_memory_pool = cp.get_default_pinned_memory_pool()

        logger.info(f"CUDA backend initialized on device {self.device.id}")

    def zeros(self, shape: tuple, dtype=np.complex128) -> "cp.ndarray":
        """
        Create zero array on GPU.

        Physical Meaning:
            Allocates zero-initialized array on GPU for 7D phase field
            computations with specified shape and dtype.

        Args:
            shape (tuple): Array shape (typically 7D for phase fields).
            dtype: Data type (default: complex128 for phase fields).

        Returns:
            cp.ndarray: Zero-initialized GPU array.
        """
        return cp.zeros(shape, dtype=dtype)

    def ones(self, shape: tuple, dtype=np.complex128) -> "cp.ndarray":
        """
        Create ones array on GPU.

        Physical Meaning:
            Allocates ones-initialized array on GPU for 7D phase field
            computations with specified shape and dtype.

        Args:
            shape (tuple): Array shape (typically 7D for phase fields).
            dtype: Data type (default: complex128 for phase fields).

        Returns:
            cp.ndarray: Ones-initialized GPU array.
        """
        return cp.ones(shape, dtype=dtype)

    def array(self, array: np.ndarray) -> "cp.ndarray":
        """
        Convert numpy array to GPU array with synchronization.

        Physical Meaning:
            Transfers array from CPU to GPU memory for 7D phase field
            computations, ensuring data consistency through explicit
            stream synchronization. For Level C, this operation must
            succeed on GPU - no CPU fallback is allowed.

        Args:
            array (np.ndarray): Input array on CPU.

        Returns:
            cp.ndarray: Array on GPU.

        Raises:
            RuntimeError: If GPU memory is insufficient with guidance
                on using block-based processing with compute_optimal_block_tiling_7d().
        """
        try:
            result = cp.asarray(array)
            # Synchronize to ensure transfer completes
            cp.cuda.Stream.null.synchronize()
            return result
        except cp.cuda.memory.OutOfMemoryError as e:
            mem_info = self.get_memory_info()
            required = array.nbytes
            available = mem_info["free_memory"]
            from .cuda_utils import raise_insufficient_memory_error

            raise raise_insufficient_memory_error(
                required_memory=required,
                available_memory=available,
                operation_name="array transfer",
                field_shape=array.shape if hasattr(array, "shape") else None,
            ) from e

    def to_numpy(self, array: "cp.ndarray") -> np.ndarray:
        """
        Convert GPU array to numpy array.

        Physical Meaning:
            Transfers array from GPU to CPU memory for analysis or
            storage, ensuring data consistency through synchronization.

        Args:
            array (cp.ndarray): Input array on GPU.

        Returns:
            np.ndarray: Array on CPU.
        """
        result = cp.asnumpy(array)
        # Synchronize to ensure transfer completes
        cp.cuda.Stream.null.synchronize()
        return result

    def fft(self, array: "cp.ndarray", axes: Optional[tuple] = None) -> "cp.ndarray":
        """
        Perform FFT on GPU with memory check and synchronization.

        Physical Meaning:
            Computes multi-dimensional FFT in spectral space for 7D phase
            field, preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. All
            operations are vectorized on GPU with explicit synchronization.
            For Level C, this operation must succeed on GPU - no CPU fallback.

        Mathematical Foundation:
            Computes F̂(k) = ∫ f(x) exp(-ik·x) dV₇ where k·x is the 7D
            inner product and dV₇ = d³x d³φ dt is the 7D volume element.
            For 7D arrays, FFT requires ~4x memory for intermediate computations.

        Args:
            array (cp.ndarray): Input array on GPU (typically 7D).
            axes (Optional[tuple]): Axes to transform (None = all axes).

        Returns:
            cp.ndarray: FFT result on GPU.

        Raises:
            RuntimeError: If GPU memory is insufficient with guidance
                on using block-based processing with compute_optimal_block_tiling_7d().
        """
        # Check available memory before FFT
        # Skip check for windows from window processing (they are calculated to fit)
        # Only check large arrays that are likely full fields, not windows
        array_size_mb = array.nbytes / (1024**2)
        # Skip check for arrays < 800MB (likely windows from window processing)
        # Windows are typically 250-400MB, so 800MB threshold is safe
        # This prevents false warnings for properly calculated windows
        if array_size_mb > 800:  # Only check arrays larger than 800MB
            if not self._check_memory_for_fft(array):
                required_memory = array.nbytes * 4  # FFT needs ~4x memory
                available_memory = self.device.mem_info[0]
                from .cuda_utils import raise_insufficient_memory_error

                raise raise_insufficient_memory_error(
                    required_memory=required_memory,
                    available_memory=available_memory,
                    operation_name="7D FFT",
                    field_shape=array.shape,
                )

        result = cp_fft.fftn(array, axes=axes)
        # Synchronize to ensure GPU operations complete
        cp.cuda.Stream.null.synchronize()
        return result

    def ifft(self, array: "cp.ndarray", axes: Optional[tuple] = None) -> "cp.ndarray":
        """
        Perform inverse FFT on GPU with memory check and synchronization.

        Physical Meaning:
            Computes multi-dimensional inverse FFT for 7D phase field,
            transforming from spectral space back to real space while
            preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. For Level C,
            this operation must succeed on GPU - no CPU fallback.

        Mathematical Foundation:
            Computes f(x) = (1/(2π)⁷) ∫ F̂(k) exp(ik·x) dk₇ where dk₇
            is the 7D spectral volume element. For 7D arrays, IFFT requires
            ~4x memory for intermediate computations.

        Args:
            array (cp.ndarray): Input array on GPU (typically 7D).
            axes (Optional[tuple]): Axes to transform (None = all axes).

        Returns:
            cp.ndarray: IFFT result on GPU.

        Raises:
            RuntimeError: If GPU memory is insufficient with guidance
                on using block-based processing with compute_optimal_block_tiling_7d().
        """
        # Check available memory before FFT
        # Skip check for windows from window processing (they are calculated to fit)
        # Only check large arrays that are likely full fields, not windows
        array_size_mb = array.nbytes / (1024**2)
        # Skip check for arrays < 800MB (likely windows from window processing)
        # Windows are typically 250-400MB, so 800MB threshold is safe
        # This prevents false warnings for properly calculated windows
        if array_size_mb > 800:  # Only check arrays larger than 800MB
            if not self._check_memory_for_fft(array):
                required_memory = array.nbytes * 4  # FFT needs ~4x memory
                available_memory = self.device.mem_info[0]
                from .cuda_utils import raise_insufficient_memory_error

                raise raise_insufficient_memory_error(
                    required_memory=required_memory,
                    available_memory=available_memory,
                    operation_name="7D IFFT",
                    field_shape=array.shape,
                )

        result = cp_fft.ifftn(array, axes=axes)
        # Synchronize to ensure GPU operations complete
        cp.cuda.Stream.null.synchronize()
        return result

    def fftshift(
        self, array: "cp.ndarray", axes: Optional[tuple] = None
    ) -> "cp.ndarray":
        """
        Perform FFT shift on GPU.

        Physical Meaning:
            Shifts zero-frequency component to center of spectrum for 7D
            phase field, preserving 7D structure.

        Args:
            array (cp.ndarray): Input array on GPU.
            axes (Optional[tuple]): Axes to shift (None = all axes).

        Returns:
            cp.ndarray: Shifted array on GPU.
        """
        return cp_fft.fftshift(array, axes=axes)

    def ifftshift(
        self, array: "cp.ndarray", axes: Optional[tuple] = None
    ) -> "cp.ndarray":
        """
        Perform inverse FFT shift on GPU.

        Physical Meaning:
            Inverse shift of zero-frequency component for 7D phase field,
            preserving 7D structure.

        Args:
            array (cp.ndarray): Input array on GPU.
            axes (Optional[tuple]): Axes to shift (None = all axes).

        Returns:
            cp.ndarray: Shifted array on GPU.
        """
        return cp_fft.ifftshift(array, axes=axes)

    def get_memory_info(self) -> dict:
        """
        Get GPU memory information.

        Physical Meaning:
            Provides detailed information about GPU memory usage and
            availability for 7D phase field computations.

        Returns:
            dict: GPU memory information including total, free, used memory
                and memory pool statistics.
        """
        mempool = cp.get_default_memory_pool()
        pinned_mempool = cp.get_default_pinned_memory_pool()

        return {
            "total_memory": self.device.mem_info[1],
            "free_memory": self.device.mem_info[0],
            "used_memory": self.device.mem_info[1] - self.device.mem_info[0],
            "mempool_used": mempool.used_bytes(),
            "mempool_total": mempool.total_bytes(),
            "pinned_used": pinned_mempool.n_free_blocks(),
            "pinned_total": pinned_mempool.n_free_blocks(),
        }

    def _check_memory_for_fft(self, array: "cp.ndarray") -> bool:
        """
        Check if there's enough GPU memory for FFT operations.

        Physical Meaning:
            FFT operations require 3-4x the input array size in memory
            for intermediate computations and output arrays in 7D space.

        Args:
            array: Input array for FFT operation.

        Returns:
            bool: True if enough memory available, False otherwise.
        """
        try:
            # Estimate memory needed for FFT (3-4x input size)
            input_size = array.nbytes
            fft_memory_needed = input_size * 4  # 4x for safety

            # Get available memory
            free_memory = self.device.mem_info[0]

            # Check if we have enough memory
            if fft_memory_needed > free_memory:
                logger.warning(
                    f"FFT requires {fft_memory_needed / (1024**2):.1f} MB, "
                    f"but only {free_memory / (1024**2):.1f} MB available"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking memory for FFT: {e}")
            return False

    @staticmethod
    def require_cuda() -> None:
        """
        Require CUDA availability, raising RuntimeError if not available.
        
        Physical Meaning:
            Enforces CUDA requirement for operations that must use GPU
            acceleration. This method should be called at the beginning
            of GPU-only code paths to fail fast if CUDA is unavailable.
            
        Raises:
            RuntimeError: If CUDA is not available with guidance on
                how to resolve the issue.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required but not available. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). CPU fallback is NOT ALLOWED."
            )
        
        # Verify CUDA device is accessible
        try:
            import cupy as cp
            cp.cuda.Device().use()
            mem_info = cp.cuda.runtime.memGetInfo()
            if mem_info[0] == 0:
                raise RuntimeError(
                    "CUDA device has no free memory. "
                    "Please free GPU memory or use a different device."
                )
        except Exception as e:
            raise RuntimeError(
                f"CUDA device is not accessible: {e}. "
                "Please check CUDA installation and GPU drivers. "
                "Verify with: nvidia-smi"
            ) from e
