"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for BVP envelope solver.

This module provides the main BVPEnvelopeSolver facade class that
coordinates all BVP envelope solver components.
"""

from .bvp_envelope_solver_base import BVPEnvelopeSolverBase
from .bvp_envelope_solver_solve import BVPEnvelopeSolverSolveMixin


class BVPEnvelopeSolver(
    BVPEnvelopeSolverBase,
    BVPEnvelopeSolverSolveMixin
):
    """
    Facade class for BVP envelope solver with all mixins.
    
    Physical Meaning:
        Solves the nonlinear 7D envelope equation for the Base High-Frequency
        Field in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, computing the envelope modulation
        that satisfies the governing equation with nonlinear stiffness and susceptibility.
    """
    pass

