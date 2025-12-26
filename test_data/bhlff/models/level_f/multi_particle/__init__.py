"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multi-particle system package.

This package contains modules for multi-particle system analysis
for Level F models in 7D phase field theory.

Physical Meaning:
    Implements multi-particle system analysis including data structures,
    potential analysis, and collective modes analysis.

Example:
    >>> from bhlff.models.level_f.multi_particle import MultiParticleSystem
    >>> system = MultiParticleSystem(domain, particles, system_params)
    >>> potential = system.compute_effective_potential()
"""

from .data_structures import Particle, SystemParameters
from .potential_analysis import PotentialAnalyzer
from .collective_modes import CollectiveModesAnalyzer

__all__ = [
    "MultiParticleSystem",
    "Particle",
    "SystemParameters",
    "PotentialAnalyzer",
    "CollectiveModesAnalyzer",
]


def __getattr__(name):
    # Lazy export to avoid circular import during package initialization
    if name == "MultiParticleSystem":
        from ..multi_particle_system import MultiParticleSystem

        return MultiParticleSystem
    raise AttributeError(name)
