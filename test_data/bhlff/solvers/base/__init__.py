"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base solvers package.

This package provides the fundamental abstract base classes for all
numerical solvers in the BHLFF framework.

Physical Meaning:
    Base solvers define the fundamental interface for solving phase field
    equations, ensuring consistent behavior across different numerical
    methods and physical regimes.

Mathematical Foundation:
    All solvers implement methods for solving the fractional Riesz
    operator L_β a = μ(-Δ)^β a + λa = s(x) and related equations.
"""

from .abstract_solver import AbstractSolver

__all__ = [
    "AbstractSolver",
]
