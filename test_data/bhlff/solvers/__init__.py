"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Solvers package for BHLFF framework.

This package provides all numerical solvers for the 7D phase field theory,
including base solvers, time integrators, and spectral methods.

Physical Meaning:
    Solvers implement the numerical methods for solving phase field equations
    in 7D space-time, providing the computational engine for the entire
    BHLFF framework.

Mathematical Foundation:
    Implements various numerical methods including finite difference,
    spectral methods, and time integration schemes for solving the
    fractional Riesz operator and related equations.
"""

from .base.abstract_solver import AbstractSolver
from .integrators import TimeIntegrator, BVPModulationIntegrator

__all__ = [
    "AbstractSolver",
    "TimeIntegrator",
    "BVPModulationIntegrator",
    # 7D spectral solvers available in core modules:
    # - bhlff.core.bvp.bvp_envelope_solver.BVPEnvelopeSolver
    # - bhlff.core.bvp.envelope_equation.solver_core.EnvelopeSolverCore7D
    # - bhlff.core.fft.fft_backend_core.FFTBackend
]
