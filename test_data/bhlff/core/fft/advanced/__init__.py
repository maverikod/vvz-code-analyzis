"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced FFT solver modules for 7D space-time.

This package provides advanced FFT solving functionality for the 7D phase field theory,
including optimization, adaptive methods, and analysis capabilities.
"""

from .fft_advanced_core import FFTAdvancedCore
from .fft_optimization import FFTOptimization
from .fft_adaptive import FFTAdaptive
from .fft_analysis import FFTAnalysis

__all__ = ["FFTAdvancedCore", "FFTOptimization", "FFTAdaptive", "FFTAnalysis"]
