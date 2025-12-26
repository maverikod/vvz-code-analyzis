"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Admittance processing submodules for Level C CUDA computations.

This package contains specialized modules for admittance computation:
- Reductions: axis-wise reductions preserving 7D geometry
- Block processing: block-based CUDA processing with 7D structure
- Optimization: optimal block tiling computation for GPU memory
- Vectorized freqs: fully vectorized frequency processing with 7D geometry
"""

from .admittance_reductions import AdmittanceReductions
from .admittance_block_processing import AdmittanceBlockProcessing
from .admittance_optimization import AdmittanceOptimization
from .admittance_vectorized_freqs import AdmittanceVectorizedFreqs

__all__ = [
    "AdmittanceReductions",
    "AdmittanceBlockProcessing",
    "AdmittanceOptimization",
    "AdmittanceVectorizedFreqs",
]
