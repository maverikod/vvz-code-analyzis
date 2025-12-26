"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

U(1)³ phase vector structure package for BVP.

This package implements the U(1)³ phase vector structure Θ_a (a=1..3)
as required by the 7D phase field theory, providing the fundamental
phase structure for the Base High-Frequency Field.

Physical Meaning:
    Implements the three-component phase vector Θ_a (a=1..3) that
    represents the fundamental phase structure of the BVP field.
    Each component corresponds to a different U(1) symmetry group,
    and together they form the U(1)³ structure required by the theory.

Mathematical Foundation:
    The phase vector Θ = (Θ₁, Θ₂, Θ₃) represents three independent
    U(1) phase degrees of freedom. The BVP field is constructed as:
    a(x) = |A(x)| * exp(i * Θ(x))
    where Θ(x) = Σ_a Θ_a(x) * e_a and e_a are the basis vectors.

Example:
    >>> from bhlff.core.bvp.phase_vector import PhaseVector
    >>> phase_vector = PhaseVector(domain, config)
    >>> theta_components = phase_vector.get_phase_components()
    >>> electroweak_currents = phase_vector.compute_electroweak_currents(envelope)
"""

from .phase_vector.phase_vector_facade import PhaseVector
from .phase_components import PhaseComponents
from .electroweak_coupling import ElectroweakCoupling

__all__ = ["PhaseVector", "PhaseComponents", "ElectroweakCoupling"]
