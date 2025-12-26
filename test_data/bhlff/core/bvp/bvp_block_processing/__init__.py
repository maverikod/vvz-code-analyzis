"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP block processing modules for 7D phase field computations.

This package contains modular components for BVP block processing,
including solvers, coefficients, boundary conditions, and iterative methods.
"""

from .bvp_block_coefficients import BVPBlockCoefficients
from .bvp_block_boundary_conditions import BVPBlockBoundaryConditions
from .bvp_block_solver import BVPBlockSolver
from .bvp_block_iterative_solver import BVPBlockIterativeSolver

__all__ = [
    "BVPBlockCoefficients",
    "BVPBlockBoundaryConditions",
    "BVPBlockSolver",
    "BVPBlockIterativeSolver",
]

