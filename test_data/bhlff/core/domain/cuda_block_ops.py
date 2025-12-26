"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA block operations helpers for `CUDABlockProcessor`.

Provides GPU implementations of per-block operations (FFT, convolution,
gradient, BVP-like placeholder) used by the facade class, keeping the class
file compact per project standards.

Theoretical Background:
    Operations are applied to blocks of the 7D field (typically spatial 3D
    slices for demonstration here) to enable CUDA acceleration with memory
    locality and reduced peak usage.

Example:
    >>> # Used internally by CUDABlockProcessor
    >>> # Do not import directly in user code
"""

from __future__ import annotations

from typing import Any

try:
    import cupy as cp
    import cupyx.scipy.ndimage as cp_ndimage
except Exception:  # pragma: no cover
    cp = None  # type: ignore
    cp_ndimage = None  # type: ignore


def process_block_fft_cuda(block_data: "cp.ndarray", _info: Any) -> "cp.ndarray":
    """Apply CUDA FFT to block and simple phase normalization on GPU."""
    fft_result = cp.fft.fftn(block_data)
    phase = cp.angle(fft_result)
    return fft_result * cp.exp(-1j * phase)


def process_block_convolution_cuda(
    block_data: "cp.ndarray", _info: Any
) -> "cp.ndarray":
    """Apply small-box convolution on GPU and return complex output."""
    kernel_shape = tuple(min(3, size) for size in block_data.shape)
    kernel = cp.ones(kernel_shape, dtype=cp.complex128) / cp.prod(kernel_shape)
    convolved = cp_ndimage.convolve(block_data.real, kernel, mode="constant")
    return convolved.astype(cp.complex128)


def process_block_gradient_cuda(block_data: "cp.ndarray", _info: Any) -> "cp.ndarray":
    """Compute gradient magnitude on GPU and return as complex array."""
    grads = cp.gradient(block_data.real)
    grad_mag = cp.sqrt(cp.sum(cp.array([g * g for g in grads]), axis=0))
    return grad_mag.astype(cp.complex128)


def process_block_bvp_cuda(block_data: "cp.ndarray", _info: Any) -> "cp.ndarray":
    """Placeholder BVP-like transform on GPU (amplitude-phase recombination)."""
    amplitude = cp.abs(block_data)
    phase = cp.angle(block_data)
    return amplitude * cp.exp(1j * phase)
