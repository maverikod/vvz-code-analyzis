"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Large-scale structure models package for 7D phase field theory.

This package implements models for large-scale structure formation
in the universe, including galaxy formation, cluster formation,
and the evolution of cosmic structures.

Theoretical Background:
    Large-scale structure formation is driven by the evolution of
    phase field configurations on cosmological scales, where
    topological defects and phase coherence give rise to observable
    structures.

Example:
    >>> from .large_scale_structure_model import LargeScaleStructureModel
    >>> structure = LargeScaleStructureModel(initial_fluctuations, params)
    >>> evolution = structure.evolve_structure(time_range)
"""

from .large_scale_structure_model import LargeScaleStructureModel
from .density_evolution import DensityEvolution
from .velocity_evolution import VelocityEvolution
from .potential_evolution import PotentialEvolution
from .structure_analysis import StructureAnalysis
from .galaxy_formation import GalaxyFormation

__all__ = [
    "LargeScaleStructureModel",
    "DensityEvolution",
    "VelocityEvolution",
    "PotentialEvolution",
    "StructureAnalysis",
    "GalaxyFormation",
]
