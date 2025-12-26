"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level F models for collective effects and multi-particle interactions.

This module implements models for studying collective effects in multi-particle
systems, including collective excitations, phase transitions, and nonlinear
interactions in the 7D phase field theory.

Theoretical Background:
    Level F represents the transition from individual defects to collective
    effects in multi-particle systems. This includes:
    - Multi-particle interactions through effective potentials
    - Collective excitations and modes
    - Phase transitions between topological states
    - Nonlinear effects in collective systems

Example:
    >>> from bhlff.models.level_f import MultiParticleSystem
    >>> system = MultiParticleSystem(domain, particles)
    >>> modes = system.find_collective_modes()
"""

from .multi_particle_system import MultiParticleSystem
from .collective import ExcitationAnalyzer, DispersionAnalyzer
from .transitions_facade import PhaseTransitions
from .nonlinear import BasicNonlinearEffects

__all__ = [
    "MultiParticleSystem",
    "ExcitationAnalyzer",
    "DispersionAnalyzer",
    "PhaseTransitions",
    "BasicNonlinearEffects",
]
