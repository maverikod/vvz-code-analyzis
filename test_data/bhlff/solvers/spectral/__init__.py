"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral solvers package.

This package provides spectral methods for solving phase field equations
using FFT and other spectral techniques.

Physical Meaning:
    Spectral solvers implement high-accuracy numerical methods for solving
    phase field equations in frequency space, providing efficient computation
    of fractional operators and related equations.

Mathematical Foundation:
    Implements spectral methods including FFT-based solvers for the fractional
    Riesz operator and related equations in frequency space.
"""

# 7D spectral solvers are available through:
# - bhlff.core.bvp.bvp_envelope_solver.BVPEnvelopeSolver
# - bhlff.core.bvp.envelope_equation.solver_core.EnvelopeSolverCore7D
# - bhlff.core.fft.fft_backend_core.FFTBackend

__all__ = [
    # 7D spectral solvers available in core modules
]
