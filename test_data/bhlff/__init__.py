"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BHLFF: 7D Phase Field Theory Implementation for Elementary Particles

This package implements the 7D phase field theory framework where elementary
particles are represented as stable phase field configurations with a three-level
structure: core, transition zone, and tail.

Physical Meaning:
    BHLFF provides numerical tools for simulating phase field dynamics in
    7-dimensional space-time, including topological defects, solitons, and
    collective phenomena. The framework is based on the Base High-Frequency
    Field (BVP) as the central backbone for all computations.

Mathematical Foundation:
    The core equation is the fractional Riesz operator:
    L_β a = μ(-Δ)^β a + λa = s(x)
    where β ∈ (0,2) is the fractional order, μ > 0 is the diffusion coefficient,
    and λ ≥ 0 is the damping parameter.

Example:
    >>> import bhlff
    >>> from bhlff.core.bvp import BVPCore
    >>> from bhlff.core.domain import Domain
    >>>
    >>> # Create domain and BVP core
    >>> domain = Domain(L=10.0, N=256, dimensions=7, N_phi=64, N_t=128, T=1.0)
    >>> bvp_core = BVPCore(domain, config)
    >>>
    >>> # Solve BVP envelope equation
    >>> import numpy as np
    >>> source = np.zeros((256, 256, 256, 64, 64, 64, 128))
    >>> source[128, 128, 128, 32, 32, 32, 64] = 1.0
    >>> envelope = bvp_core.solve_envelope(source)
"""

__version__ = "0.1.0"
__author__ = "Vasiliy Zdanovskiy"
__email__ = "vasilyvz@gmail.com"
__license__ = "MIT"

# Core imports
from .core.domain import Domain
from .core.domain.parameters import Parameters
from .core.bvp.bvp_core import BVPCore

# Version info
__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "Domain",
    "Parameters",
    "BVPCore",
]
