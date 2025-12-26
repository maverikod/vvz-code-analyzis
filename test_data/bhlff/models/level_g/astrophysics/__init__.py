"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Astrophysical object models package for 7D phase field theory.

This package provides models for astrophysical objects (stars, galaxies,
black holes) as phase field configurations with specific topological
properties and observable characteristics.

Theoretical Background:
    Astrophysical objects are represented as phase field configurations
    with specific topological properties that give rise to their
    observable characteristics through phase coherence and defects.

Example:
    >>> from .astrophysical_object_model import AstrophysicalObjectModel
    >>> star = AstrophysicalObjectModel('star', stellar_params)
    >>> galaxy = AstrophysicalObjectModel('galaxy', galactic_params)
"""

from .astrophysical_object_model import AstrophysicalObjectModel
from .stellar_models import StellarModel
from .galactic_models import GalacticModel
from .black_hole_models import BlackHoleModel

__all__ = [
    "AstrophysicalObjectModel",
    "StellarModel",
    "GalacticModel",
    "BlackHoleModel",
]
