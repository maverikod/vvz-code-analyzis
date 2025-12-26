"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

FFT backend implementation.

This module provides the FFT backend for efficient spectral operations
in the 7D phase field theory.

Physical Meaning:
    FFT backend implements the computational engine for spectral methods,
    providing efficient transformation between real and frequency space
    for phase field calculations.

Mathematical Foundation:
    Implements Fast Fourier Transform operations for efficient computation
    of spectral methods in phase field equations.

Example:
    >>> backend = FFTBackend(domain, plan_type="MEASURE")
    >>> spectral_data = backend.fft(real_data)
    >>> real_data = backend.ifft(spectral_data)
"""

from .fft_backend_core import FFTBackend
