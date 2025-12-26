"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA utilities for GPU acceleration in BHLFF with 7D phase field support.

This module provides CUDA detection, backend selection, and utility functions
for 7D phase field calculations. For Level C code paths, CUDA is required with
no CPU fallback. All operations use block-based processing optimized for 80%
GPU memory usage with vectorized operations and explicit stream synchronization.

Physical Meaning:
    CUDA acceleration is critical for 7D phase field calculations in space-time
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ due to the high computational complexity of spectral
    operations in 7D. This module provides backend selection, detection, and
    block processing utilities with optimal GPU memory utilization.

Theoretical Background:
    The 7D phase field theory operates in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, where:
    - Spatial coordinates: x ∈ ℝ³ (dimensions 0, 1, 2)
    - Phase coordinates: φ ∈ 𝕋³ (dimensions 3, 4, 5)
    - Time: t ∈ ℝ (dimension 6)
    All operations preserve 7D structure and use vectorized GPU kernels with
    block-based processing for optimal memory usage (80% of GPU memory).

Example:
    >>> from bhlff.utils.cuda_utils import get_cuda_backend_required
    >>> backend = get_cuda_backend_required()
    >>> array = backend.zeros((64, 64, 64, 16, 16, 16, 100))
    >>> block_tiling = backend.compute_optimal_block_tiling_7d(array.shape)
"""

import logging
import os
from typing import Optional, Union

# Import backend classes
from .cuda_backend import CUDABackend, CUDA_AVAILABLE
from .cpu_backend import CPUBackend, NUMPY_FFT_AVAILABLE
from ..core.exceptions import CUDANotAvailableError, InsufficientGPUMemoryError

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "CUDABackend",
    "CPUBackend",
    "CUDA_AVAILABLE",
    "NUMPY_FFT_AVAILABLE",
    "detect_cuda_availability",
    "get_cuda_backend_required",
    "get_optimal_backend",
    "get_backend_info",
    "get_global_backend",
    "reset_global_backend",
    "check_level_c_cuda_required",
    "raise_insufficient_memory_error",
    "calculate_optimal_window_memory",
]


def detect_cuda_availability() -> bool:
    """
    Detect if CUDA is available and working.

    Physical Meaning:
        Checks if CUDA is properly installed and functional for 7D phase
        field calculations with comprehensive testing of GPU operations.

    Returns:
        bool: True if CUDA is available and working.
    """
    if not CUDA_AVAILABLE:
        return False

    try:
        import cupy as cp

        # Test basic CUDA operations
        test_array = cp.zeros((10, 10), dtype=cp.complex128)
        result = cp.fft.fft(test_array)
        cp.asnumpy(result)  # Test GPU->CPU transfer

        # Check if we can allocate reasonable memory
        test_large = cp.zeros((100, 100, 100), dtype=cp.complex128)
        del test_large

        return True
    except Exception as e:
        logger.warning(f"CUDA detection failed: {e}")
        return False


def get_cuda_backend_required() -> CUDABackend:
    """
    Get CUDA backend - required for Level C code paths.

    Physical Meaning:
        Returns CUDA backend instance, raising error if CUDA is not available.
        This function is used by Level C code paths which require GPU
        acceleration and do not support CPU fallback. All Level C operations
        must use this function to ensure GPU-only execution.

    Returns:
        CUDABackend: CUDA backend instance.

    Raises:
        RuntimeError: If CUDA is not available or detection fails with
            guidance on how to resolve the issue.
    """
    if not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA not available. Level C requires GPU acceleration. "
            "Please install CuPy and ensure CUDA is properly configured. "
            "Install with: pip install cupy-cuda11x or cupy-cuda12x "
            "(matching your CUDA version)."
        )

    if not detect_cuda_availability():
        raise RuntimeError(
            "CUDA detection failed. Level C requires functional GPU. "
            "Please check CUDA installation and GPU drivers. "
            "Verify CUDA installation with: nvidia-smi"
        )

    try:
        backend = CUDABackend()
        logger.info(
            "CUDA backend initialized for Level C (GPU required, no CPU fallback)"
        )
        return backend
    except Exception as e:
        raise RuntimeError(
            f"CUDA backend initialization failed: {e}. "
            f"Level C requires GPU acceleration. "
            f"Ensure GPU is available and CUDA drivers are properly installed."
        ) from e


def get_optimal_backend() -> CUDABackend:
    """
    Get CUDA backend - CPU fallback is NOT ALLOWED.

    Physical Meaning:
        Returns CUDA backend instance, raising error if CUDA is not available.
        This function requires GPU acceleration - NO CPU fallback is allowed.
        All operations must use CUDA.

    WARNING:
        This function requires CUDA and will raise RuntimeError if CUDA is not available.
        CPU fallback is NOT ALLOWED in this project.

    Returns:
        CUDABackend: CUDA backend instance.

    Raises:
        RuntimeError: If CUDA is not available or initialization fails.
    """
    # Check environment variable override
    force_cuda = os.getenv("BHLFF_FORCE_CUDA", "false").lower() == "true"

    if force_cuda and not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA forced but not available. "
            "Please install CuPy and ensure CUDA is properly configured."
        )

    if not CUDA_AVAILABLE:
        raise CUDANotAvailableError(
            "CUDA not available. GPU acceleration is required. "
            "Please install CuPy and ensure CUDA is properly configured. "
            "Install with: pip install cupy-cuda11x or cupy-cuda12x "
            "(matching your CUDA version). CPU fallback is NOT ALLOWED."
        )

    if not detect_cuda_availability():
        raise CUDANotAvailableError(
            "CUDA detection failed. GPU acceleration is required. "
            "Please check CUDA installation and GPU drivers. "
            "Verify CUDA installation with: nvidia-smi. "
            "CPU fallback is NOT ALLOWED."
        )

    try:
        backend = CUDABackend()
        logger.info("CUDA backend initialized (CPU fallback disabled)")
        return backend
    except Exception as e:
        raise CUDANotAvailableError(
            f"CUDA backend initialization failed: {e}. "
            f"GPU acceleration is required. "
            f"Ensure GPU is available and CUDA drivers are properly installed. "
            f"CPU fallback is NOT ALLOWED."
        ) from e


def get_backend_info() -> dict:
    """
    Get information about the current CUDA backend.

    Physical Meaning:
        Provides detailed information about the CUDA backend
        being used for 7D phase field calculations. CPU fallback is NOT ALLOWED.

    Returns:
        dict: Backend information including type, memory, and capabilities.
    """
    backend = get_optimal_backend()

    info = {
        "type": "CUDA",
        "cuda_available": CUDA_AVAILABLE,
        "numpy_fft_available": NUMPY_FFT_AVAILABLE,
        "memory_info": backend.get_memory_info(),
        "device_id": backend.device.id,
    }

    try:
        info["device_name"] = backend.device.name
    except Exception:
        info["device_name"] = "Unknown"

    return info


# Global backend instance for automatic use (CUDA only, no CPU fallback)
_global_backend: Optional[CUDABackend] = None


def get_global_backend() -> CUDABackend:
    """
    Get the global CUDA backend instance.

    Physical Meaning:
        Returns the global CUDA backend instance for use throughout the BHLFF
        framework, ensuring consistent GPU usage. CPU fallback is NOT ALLOWED.

    Returns:
        CUDABackend: Global CUDA backend instance.
    """
    global _global_backend
    if _global_backend is None:
        _global_backend = get_optimal_backend()
    return _global_backend


def reset_global_backend() -> None:
    """
    Reset the global backend instance.

    Physical Meaning:
        Resets the global backend to allow re-detection of optimal backend
        configuration.
    """
    global _global_backend
    _global_backend = None


def check_level_c_cuda_required(backend: CUDABackend) -> None:
    """
    Verify that backend is CUDA for Level C code paths.

    Physical Meaning:
        Ensures that Level C code paths use GPU-only execution by verifying
        that the backend is CUDA, not CPU. This function should be called
        at the beginning of Level C methods to prevent CPU fallback.

    Args:
        backend (Union[CUDABackend, CPUBackend]): Backend instance to check.

    Raises:
        RuntimeError: If backend is not CUDA with guidance on using
            get_cuda_backend_required() instead.
    """
    if not isinstance(backend, CUDABackend):
        raise RuntimeError(
            f"Level C requires CUDA backend, but got {type(backend).__name__}. "
            f"Use get_cuda_backend_required() instead of get_optimal_backend() "
            f"for Level C code paths. Level C does not support CPU fallback."
        )


def raise_insufficient_memory_error(
    required_memory: int,
    available_memory: int,
    operation_name: str = "operation",
    field_shape: Optional[tuple] = None,
) -> InsufficientGPUMemoryError:
    """
    Raise informative error for insufficient GPU memory with guidance.

    Physical Meaning:
        Provides detailed error message with guidance on using block-based
        processing when GPU memory is insufficient for 7D phase field
        operations. For Level C, block processing is required for large fields.

    Mathematical Foundation:
        For 7D operations, memory requirements scale as:
        - Input field: 1x
        - Output field: 1x
        - Intermediate operations: 2-4x
        - FFT workspace: 2x
        - Reduction buffers: 1x
        Total overhead: ~10x for complex 7D operations

    Args:
        required_memory (int): Required memory in bytes.
        available_memory (int): Available memory in bytes.
        operation_name (str): Name of the operation (default: "operation").
        field_shape (Optional[tuple]): Shape of the field array if available.

    Returns:
        InsufficientGPUMemoryError: Error with detailed guidance on block processing.
    """
    return InsufficientGPUMemoryError(
        required_memory=required_memory,
        available_memory=available_memory,
        operation_name=operation_name,
        field_shape=field_shape
    )


def calculate_optimal_window_memory(
    gpu_memory_ratio: float = 0.8,
    overhead_factor: float = 4.0,
    logger: Optional[logging.Logger] = None,
) -> tuple[int, float, float]:
    """
    Calculate optimal window/block memory size based on TOTAL GPU memory.
    
    Physical Meaning:
        Calculates optimal window/block size for GPU processing based on
        TOTAL GPU memory (not free), adapting to card size. Uses 80% of
        total memory as safety limit, with 20% reserve covering minor overflows.
        
    Mathematical Foundation:
        - base_memory = total_memory * gpu_memory_ratio (80% limit)
        - window_memory = base_memory / fft_factor
        - fft_factor depends on card size:
          * Small cards (<4GB): 4.5 (conservative)
          * Medium cards (4-16GB): 3.8 (moderate)
          * Large cards (>16GB): 3.5 (aggressive)
        - Actual usage = window_memory * overhead_factor
        
    Args:
        gpu_memory_ratio (float): GPU memory utilization ratio (default: 0.8).
        overhead_factor (float): Memory overhead factor for operations (default: 4.0).
        logger (Optional[logging.Logger]): Logger instance for info messages.
        
    Returns:
        tuple[int, float, float]: (max_window_elements, actual_usage_gb, actual_usage_pct)
            - max_window_elements: Maximum elements per window/block
            - actual_usage_gb: Actual memory usage in GB with overhead
            - actual_usage_pct: Actual memory usage as percentage of total
    """
    if not CUDA_AVAILABLE:
        # CPU fallback: use 1GB window
        max_window_elements = int(1e9 // 16)  # complex128 = 16 bytes
        return max_window_elements, 0.0, 0.0
    
    try:
        import cupy as cp
        mem_info = cp.cuda.runtime.memGetInfo()
        free_memory = mem_info[0]
        total_memory = mem_info[1]
        
        # Calculate window size based on TOTAL memory, not free
        # Use 80% of TOTAL memory as base (safety limit to avoid hard reset)
        # 20% reserve covers minor overflows
        base_memory = int(total_memory * gpu_memory_ratio)
        
        # Factor depends on card size (more aggressive for larger cards):
        # - Small cards (<4GB): conservative (4.5) - window*4 = 80%*4/4.5 = 71% of total
        # - Medium cards (4-16GB): moderate (3.8) - window*4 = 80%*4/3.8 = 84% of total (20% reserve covers)
        # - Large cards (>16GB): aggressive (3.5) - window*4 = 80%*4/3.5 = 91% of total (20% reserve covers)
        if total_memory < 4 * 1024**3:  # < 4GB
            fft_factor = 4.5  # Conservative for small cards
        elif total_memory < 16 * 1024**3:  # 4-16GB
            fft_factor = 3.8  # Moderate: slight overflow covered by 20% reserve
        else:  # > 16GB
            fft_factor = 3.5  # Aggressive: overflow covered by 20% reserve, maximizes utilization
        
        window_memory = int(base_memory / fft_factor)
        bytes_per_element = 16  # complex128
        max_window_elements = window_memory // bytes_per_element
        
        # CRITICAL: Ensure window with overhead doesn't exceed 80% of TOTAL memory
        # This prevents hard reset by ensuring we never exceed the safety limit
        max_window_with_overhead = int(base_memory / overhead_factor)
        max_window_elements_safe = max_window_with_overhead // bytes_per_element
        
        # Use the safer limit (window with overhead must fit in 80% of total)
        max_window_elements = min(max_window_elements, max_window_elements_safe)
        
        # Also check free memory as additional safety (but don't let it override total-based calculation)
        # Only if free memory is very low (< 20% of total), reduce window size
        if free_memory < 0.2 * total_memory:
            max_window_from_free = int(free_memory * 0.9 / fft_factor)  # Use 90% of free
            max_window_elements = min(max_window_elements, max_window_from_free // bytes_per_element)
            if logger:
                logger.warning(
                    f"Free memory is low ({free_memory/1e9:.2f}GB < 20% of total), "
                    f"reducing window size to {max_window_elements/1e6:.1f}M elements"
                )
        
        # Calculate actual memory usage with overhead
        actual_usage = (max_window_elements * bytes_per_element * overhead_factor) / (1024**3)
        actual_usage_pct = (actual_usage / (total_memory / (1024**3))) * 100
        
        # CRITICAL SAFETY CHECK: Ensure we never exceed 80% even with overhead
        if actual_usage_pct > 80.0:
            # Reduce window size to ensure we stay under 80%
            max_window_elements = int((total_memory * 0.8 / overhead_factor) // bytes_per_element)
            actual_usage = (max_window_elements * bytes_per_element * overhead_factor) / (1024**3)
            actual_usage_pct = (actual_usage / (total_memory / (1024**3))) * 100
            if logger:
                logger.warning(
                    f"Window size reduced to stay under 80% limit: "
                    f"{max_window_elements/1e6:.1f}M elements, {actual_usage_pct:.1f}% of total"
                )
        
        if logger:
            logger.info(
                f"GPU memory: free={free_memory/1e9:.2f}GB, total={total_memory/1e9:.2f}GB, "
                f"base={base_memory/1e9:.2f}GB (80% limit), fft_factor={fft_factor:.1f}, "
                f"max_window={max_window_elements/1e6:.1f}M elements "
                f"({max_window_elements*bytes_per_element/1e6:.1f}MB), "
                f"usage={actual_usage:.2f}GB ({actual_usage_pct:.1f}% of total)"
            )
        
        return max_window_elements, actual_usage, actual_usage_pct
        
    except Exception as e:
        if logger:
            logger.warning(f"Failed to get GPU memory info: {e}")
        # Fallback: use 1GB window
        max_window_elements = int(1e9 // 16)
        return max_window_elements, 0.0, 0.0
