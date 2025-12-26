"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton analysis solutions package for Level F models.

This package implements complete soliton analysis functionality
for nonlinear systems in 7D phase field theory, including
single, two, and three-soliton solutions with full optimization.

Physical Meaning:
    Provides comprehensive soliton solution finding and analysis
    using 7D BVP theory with fractional Laplacian equations
    and soliton-soliton interactions.

Example:
    >>> from bhlff.models.level_f.nonlinear.soliton_analysis import SolitonAnalysisSolutions
    >>> solver = SolitonAnalysisSolutions(system, nonlinear_params)
    >>> solutions = solver.find_soliton_solutions()
"""

from .base import SolitonAnalysisBase
from .single_soliton import SingleSolitonSolver
from .multi_soliton_solutions import MultiSolitonSolutions
from .multi_soliton_core import MultiSolitonCore

__all__ = [
    "SolitonAnalysisBase",
    "SingleSolitonSolver",
    "MultiSolitonSolutions",
    "MultiSolitonCore",
]
