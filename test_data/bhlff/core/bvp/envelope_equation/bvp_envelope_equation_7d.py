"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main 7D BVP envelope equation implementation.

This module provides the main BVPEnvelopeEquation7D class that coordinates
the solution of the 7D envelope equation using the modular components.

Physical Meaning:
    The main envelope equation class coordinates the solution of the full
    7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, including
    spatial, phase, and temporal derivatives with nonlinear terms.

Mathematical Foundation:
    Solves the 7D envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    using modular derivative operators and nonlinear terms.

Example:
    >>> equation_7d = BVPEnvelopeEquation7D(domain_7d, config)
    >>> envelope = equation_7d.solve_envelope(source_7d)
"""

from .bvp_envelope_equation_7d_facade import BVPEnvelopeEquation7D
