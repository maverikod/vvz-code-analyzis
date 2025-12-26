"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized modules for Level E experiments.

This package provides GPU-accelerated implementations of soliton and defect
computations with block processing and vectorization for maximum performance.
"""

from .soliton_energy_cuda import SolitonEnergyCalculatorCUDA
from .soliton_optimization_cuda import SolitonOptimizerCUDA
from .defect_dynamics_cuda import DefectDynamicsCUDA

__all__ = [
    "SolitonEnergyCalculatorCUDA",
    "SolitonOptimizerCUDA",
    "DefectDynamicsCUDA",
]
