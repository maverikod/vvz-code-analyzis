"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for FFT solver 7D modules.

Brief description of the module's purpose and its role in the 7D phase field theory.

Detailed description of the module's functionality, including:
- Physical meaning and theoretical background
- Key algorithms and methods implemented
- Dependencies and relationships with other modules
- Usage examples and typical workflows

Theoretical Background:
    Provides a single import point for 7D FFT solvers used to solve the
    fractional Riesz operator L_β = μ(-Δ)^β + λ in spectral space across the
    7D manifold M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Example:
    >>> from bhlff.core.fft.fft_solver_7d import FFTSolver7D
    >>> solver = FFTSolver7D(domain, {"mu": 1.0, "beta": 1.0, "lambda": 0.0})
"""

from .fft_solver_7d_basic import FFTSolver7DBasic
from .fft_solver_7d_advanced import FFTSolver7DAdvanced

# Alias for backward compatibility and default advanced implementation
FFTSolver7D = FFTSolver7DAdvanced

__all__ = ["FFTSolver7DBasic", "FFTSolver7DAdvanced", "FFTSolver7D"]
