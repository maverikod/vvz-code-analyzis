"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase field package for 7D BVP theory.

This package contains implementations of phase field structures for the 7D BVP theory,
including U(1)³ phase fields and related functionality.

Physical Meaning:
    Implements phase field structures that represent the fundamental
    phase degrees of freedom in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Provides implementations of:
    - U(1)³ phase fields a(x,φ,t) ∈ ℂ³
    - Phase coherence analysis
    - Gauge transformations
    - Phase field operations

Example:
    >>> from bhlff.core.phase import U1PhaseField
    >>> phase_field = U1PhaseField(domain)
    >>> coherence = phase_field.compute_phase_coherence()
"""

from .u1_phase_field import U1PhaseField

__all__ = ["U1PhaseField"]
