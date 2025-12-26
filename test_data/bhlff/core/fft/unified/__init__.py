"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Unified FFT package facade exports for 7D BHLFF Framework.

This package provides a modular, CUDA-optimized implementation of unified
spectral operations with a small facade surface and helper modules for
CPU/GPU FFTs, filters, wave-vector utilities, blocked processing, and
planning/normalization.

Theoretical Background:
    Spectral operations implement mathematical operations in frequency space
    for 7D computations with U(1)^3 phase structure.

Example:
    >>> from bhlff.core.fft.unified import UnifiedSpectralOperations
    >>> ops = UnifiedSpectralOperations(domain, precision="float64")
    >>> spec = ops.forward_fft(field, "physics")
    >>> real = ops.inverse_fft(spec, "physics")
"""

from .facade import UnifiedSpectralOperations

__all__ = ["UnifiedSpectralOperations"]
