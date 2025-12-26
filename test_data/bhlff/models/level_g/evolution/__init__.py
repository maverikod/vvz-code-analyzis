"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological evolution package for 7D phase field theory.

This package implements the cosmological evolution of phase fields
in expanding universe, including the integration of evolution
equations and analysis of cosmological parameters.

Theoretical Background:
    The cosmological evolution module implements the time evolution
    of phase fields in expanding spacetime, where the phase field
    represents the fundamental field that drives structure formation.

Example:
    >>> from .cosmological_evolution import CosmologicalEvolution
    >>> evolution = CosmologicalEvolution(initial_conditions, params)
    >>> results = evolution.evolve_cosmology(time_range)
"""

from .cosmological_evolution import CosmologicalEvolution
from .phase_field_evolution import PhaseFieldEvolution
from .structure_formation import StructureFormation
from .cosmological_parameters import CosmologicalParameters
from .evolution_analysis import EvolutionAnalysis

__all__ = [
    "CosmologicalEvolution",
    "PhaseFieldEvolution",
    "StructureFormation",
    "CosmologicalParameters",
    "EvolutionAnalysis",
]
