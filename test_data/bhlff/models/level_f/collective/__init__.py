"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Collective excitations module for Level F models.

This module provides analysis tools for collective excitations in multi-particle
systems, including excitation analysis and dispersion relations.

Physical Meaning:
    Collective excitations represent coherent modes of oscillation in
    multi-particle systems, where particles move in a correlated manner.
    These excitations are fundamental for understanding phase transitions
    and collective behavior in the 7D phase field theory.

Mathematical Foundation:
    Collective excitations are described by dispersion relations that
    relate frequency to wave number, characterizing the propagation
    of coherent modes through the system.
"""

from .excitation_analysis import ExcitationAnalyzer
from .dispersion_analysis import DispersionAnalyzer

# Re-export facade class from dedicated facade module to avoid circular import
from ..collective_facade import CollectiveExcitations

__all__ = [
    "ExcitationAnalyzer",
    "DispersionAnalyzer",
    "CollectiveExcitations",
]
