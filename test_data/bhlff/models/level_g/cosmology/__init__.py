"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological models package for 7D phase field theory.

This package implements envelope-derived effective metric models
for the 7D phase field theory without invoking spacetime curvature
or cosmological scale factors.

Theoretical Background:
    Gravity-like effects emerge from the curvature of the VBP envelope
    in the 7D phase field theory. There is no spacetime curvature here;
    instead, an effective metric g_eff[Θ] is derived from envelope
    invariants and phase dynamics.

Example:
    >>> from .cosmological_model import CosmologicalModel
    >>> cosmology = CosmologicalModel(initial_conditions, params)
    >>> evolution = cosmology.evolve_universe([0, 13.8])
"""

from .cosmological_model import CosmologicalModel
from .envelope_effective_metric import EnvelopeEffectiveMetric
from .phase_field_evolution import PhaseFieldEvolution
from .structure_formation import StructureFormation
from .cosmological_parameters import CosmologicalParameters

__all__ = [
    "CosmologicalModel",
    "EnvelopeEffectiveMetric",
    "PhaseFieldEvolution",
    "StructureFormation",
    "CosmologicalParameters",
]
