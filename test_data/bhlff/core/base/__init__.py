"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base module for BHLFF core components.

This module contains abstract base classes and interfaces for all
computational components in the BHLFF framework.

Physical Meaning:
    Base classes provide the fundamental interfaces and common
    functionality for all solvers, fields, and computational components
    in the 7D phase field theory implementation.

Mathematical Foundation:
    Base classes implement common mathematical operations and interfaces
    required for solving the fractional Riesz operator and related
    equations in 7D space-time.
"""

from .abstract_solver import AbstractSolver
from .field import Field

__all__ = [
    "AbstractSolver",
    "Field",
]
