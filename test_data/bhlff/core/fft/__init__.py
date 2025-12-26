"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

FFT package for 7D BHLFF framework.

This package provides FFT operations and spectral methods for the 7D phase
field theory, including optimized solvers for fractional operators and
memory management for large-scale computations.

Physical Meaning:
    FFT components implement spectral methods for efficient computation
    of 7D phase field equations in frequency space with U(1)³ phase structure.

Mathematical Foundation:
    Implements FFT-based spectral methods for solving 7D phase field equations
    including fractional Laplacian operators, spectral operations, and
    optimized FFT planning for 7D computations.

Example:
    >>> from bhlff.core.fft import FFTSolver7D, FractionalLaplacian
    >>> solver = FFTSolver7D(domain, parameters)
    >>> solution = solver.solve_stationary(source_field)
"""

from .fft_backend import FFTBackend
from .spectral_operations import SpectralOperations
from .fft_solver_7d import FFTSolver7D

# Note: FractionalLaplacian is provided by operators package
from bhlff.core.operators.fractional_laplacian import FractionalLaplacian
from .memory_manager_7d import MemoryManager7D
from .fft_plan_7d import FFTPlan7D
from .spectral_coefficient_cache import SpectralCoefficientCache

__all__ = [
    "FFTBackend",
    "SpectralOperations",
    "FFTSolver7D",
    "FractionalLaplacian",
    "MemoryManager7D",
    "FFTPlan7D",
    "SpectralCoefficientCache",
]
