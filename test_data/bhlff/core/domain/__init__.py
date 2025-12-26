"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Domain package for computational domain and field management.

This package provides the fundamental components for defining computational
domains, managing field data, and handling parameters for 7D phase field
theory simulations.

Physical Meaning:
    The domain represents the computational space where phase field
    configurations are defined and evolved, providing the mathematical
    foundation for spatial discretization and field operations.

Mathematical Foundation:
    Implements the computational domain with proper grid generation,
    boundary condition handling, and field data management for
    solving phase field equations in 7D space-time.
"""

from .domain import Domain
from .field import Field
from .parameters import Parameters

__all__ = [
    "Domain",
    "Field",
    "Parameters",
]
