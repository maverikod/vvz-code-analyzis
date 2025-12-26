"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-accelerated Level G modules.

This package provides GPU-optimized implementations for Level G models
(cosmology, large-scale structure, and gravitational effects) using
vectorization and block processing. It leverages CuPy when available
and falls back to NumPy otherwise.

Physical Meaning:
    Enables efficient computation for cosmological-scale simulations
    and envelope-based gravitational effects in the 7D phase field
    theory by exploiting GPU parallelism and memory-aware block
    processing.
"""

from .cosmology_cuda import CosmologicalEvolutionCUDA
from .structure_cuda import LargeScaleStructureAnalyzerCUDA
from .gravity_cuda import GravitationalEffectsCUDA

__all__ = [
    "CosmologicalEvolutionCUDA",
    "LargeScaleStructureAnalyzerCUDA",
    "GravitationalEffectsCUDA",
]
