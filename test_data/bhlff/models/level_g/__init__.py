"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level G models for cosmological and astrophysical applications.

This module implements the highest level of the 7D phase field theory,
including cosmological evolution, large-scale structure formation,
astrophysical objects, and gravitational effects.

Theoretical Background:
    Level G represents the cosmological and astrophysical applications
    of the 7D phase field theory, where the phase field operates on
    the largest scales of the universe and manifests as observable
    astrophysical phenomena.

Example:
    >>> from bhlff.models.level_g import CosmologicalModel
    >>> cosmology = CosmologicalModel(initial_conditions, params)
    >>> evolution = cosmology.evolve_universe(time_range)
"""

from .cosmology import CosmologicalModel, EnvelopeEffectiveMetric
from .astrophysics import AstrophysicalObjectModel
from .gravity import VBPGravitationalEffectsModel
from .structure import LargeScaleStructureModel
from .evolution import CosmologicalEvolution
from .analysis import CosmologicalAnalysis
from .validation import ParticleInversion, ParticleValidation

__all__ = [
    "CosmologicalModel",
    "EnvelopeEffectiveMetric",
    "AstrophysicalObjectModel",
    "VBPGravitationalEffectsModel",
    "LargeScaleStructureModel",
    "CosmologicalEvolution",
    "CosmologicalAnalysis",
    "ParticleInversion",
    "ParticleValidation",
]
