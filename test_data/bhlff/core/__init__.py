"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core module for BHLFF package.

This module contains the fundamental components of the BHLFF framework,
including domain definitions, parameter management, BVP core, and base classes
for all computational components.

Physical Meaning:
    The core module provides the mathematical foundation for the 7D phase
    field theory implementation, including the computational domain,
    parameter validation, BVP framework, and base interfaces for all "
    "solvers and models.

Mathematical Foundation:
    Core components implement the fundamental mathematical structures
    required for solving the fractional Riesz operator and related
    equations in 7D space-time, with BVP as the central backbone.
"""

from .domain import Domain, Field
from .domain.parameters import Parameters
from .bvp import (
    BVPCore,
    BVPEnvelopeSolver,
    BVPImpedanceCalculator,
    BVPInterface,
    BVPConstants,
    QuenchDetector,
)
from .operators import OperatorRiesz, FractionalLaplacian, MemoryKernel
from .fft import FFTBackend, SpectralOperations
from .sources import Source, BVPSource

__all__ = [
    "Domain",
    "Field",
    "Parameters",
    "BVPCore",
    "BVPEnvelopeSolver",
    "BVPImpedanceCalculator",
    "BVPInterface",
    "BVPConstants",
    "QuenchDetector",
    "OperatorRiesz",
    "FractionalLaplacian",
    "MemoryKernel",
    "FFTBackend",
    "SpectralOperations",
    "Source",
    "BVPSource",
]
