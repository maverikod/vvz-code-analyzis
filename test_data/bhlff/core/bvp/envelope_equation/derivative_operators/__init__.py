"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Derivative operators package for 7D BVP envelope equation.

This package provides modular derivative operators for the 7D BVP envelope
equation, including spatial, phase, and temporal operators with appropriate
boundary conditions and numerical schemes.

Physical Meaning:
    The derivative operators package implements all derivative operations
    needed for the 7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
    including spatial gradients/divergences, phase gradients/divergences,
    and temporal derivatives.

Mathematical Foundation:
    Provides finite difference operators for spatial coordinates,
    periodic operators for phase coordinates, and backward difference
    operators for temporal evolution.

Example:
    >>> from .spatial_operators import SpatialOperators
    >>> from .phase_operators import PhaseOperators
    >>> from .temporal_operators import TemporalOperators
    >>> spatial_ops = SpatialOperators(domain_7d)
    >>> phase_ops = PhaseOperators(domain_7d)
    >>> temporal_ops = TemporalOperators(domain_7d)
"""

from .spatial_operators import SpatialOperators
from .phase_operators import PhaseOperators
from .temporal_operators import TemporalOperators

__all__ = ["SpatialOperators", "PhaseOperators", "TemporalOperators"]
