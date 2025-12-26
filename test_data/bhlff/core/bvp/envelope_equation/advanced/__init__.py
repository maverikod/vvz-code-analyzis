"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced envelope equation solver modules.

This package provides advanced solving functionality for the 7D BVP envelope
equation, including adaptive methods, preconditioning, and optimization.
"""

from .solver_advanced_core import SolverAdvancedCore
from .solver_adaptive import SolverAdaptive
from .solver_optimized import SolverOptimized
from .solver_preconditioning import SolverPreconditioning

__all__ = [
    "SolverAdvancedCore",
    "SolverAdaptive",
    "SolverOptimized",
    "SolverPreconditioning",
]
