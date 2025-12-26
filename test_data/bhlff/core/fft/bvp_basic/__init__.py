"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Comprehensive BVP solver modules for 7D envelope equation.

This package provides comprehensive BVP solving functionality for the 7D envelope equation,
including core residual computation, Jacobian calculation, and theoretical validation.
"""

from .bvp_basic_core import BVPCoreSolver
from .bvp_residual import BVPResidual
from .bvp_jacobian import BVPJacobian
from .bvp_linear_solver import BVPLinearSolver

__all__ = ["BVPCoreSolver", "BVPResidual", "BVPJacobian", "BVPLinearSolver"]
