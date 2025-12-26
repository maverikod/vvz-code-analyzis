"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP envelope equation package for 7D space-time theory.

This package contains the modular implementation of the 7D BVP envelope equation,
solving the nonlinear envelope equation in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    The envelope equation describes the evolution of the BVP field envelope
    in 7D space-time, including spatial, phase, and temporal derivatives
    with nonlinear stiffness and susceptibility terms.

Mathematical Foundation:
    Solves the 7D envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where:
    - κ(|a|) = κ₀ + κ₂|a|² (nonlinear stiffness)
    - χ(|a|) = χ' + iχ''(|a|) (effective susceptibility with quenches)
    - s(x,φ,t) is the source term

Example:
    >>> from bhlff.core.bvp.envelope_equation import BVPEnvelopeEquation7D
    >>> equation_7d = BVPEnvelopeEquation7D(domain_7d, config)
    >>> envelope = equation_7d.solve_envelope(source_7d)
"""

from .bvp_envelope_equation_7d import BVPEnvelopeEquation7D
from .derivative_operators_facade import DerivativeOperators7D
from .nonlinear_terms import NonlinearTerms7D
from .solver_core import EnvelopeSolverCore7D

__all__ = [
    "BVPEnvelopeEquation7D",
    "DerivativeOperators7D",
    "NonlinearTerms7D",
    "EnvelopeSolverCore7D",
]
