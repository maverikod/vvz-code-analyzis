"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for FFT solver 7D basic.

This module provides the main FFTSolver7DBasic facade class that
coordinates all FFT solver 7D basic components.
"""

from .fft_solver_7d_basic_base import FFTSolver7DBasicBase
from .fft_solver_7d_basic_solve import FFTSolver7DBasicSolveMixin
from .fft_solver_7d_basic_coefficients import FFTSolver7DBasicCoefficientsMixin
from .fft_solver_7d_basic_operator import FFTSolver7DBasicOperatorMixin


class FFTSolver7DBasic(
    FFTSolver7DBasicBase,
    FFTSolver7DBasicSolveMixin,
    FFTSolver7DBasicCoefficientsMixin,
    FFTSolver7DBasicOperatorMixin
):
    """
    Facade class for full-array FFT-based 7D solver with all mixins.
    
    Physical Meaning:
        Solves the stationary 7D fractional Riesz equation in spectral space
        with orthonormal FFT normalization.
    """
    pass

