"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Astrophysical object models facade for 7D phase field theory.

This module provides a facade interface for astrophysical object models,
delegating to specialized modules for different object types.

Theoretical Background:
    Astrophysical objects are represented as phase field configurations
    with specific topological properties that give rise to their
    observable characteristics through phase coherence and defects.

Example:
    >>> from .astrophysics import AstrophysicalObjectModel
    >>> star = AstrophysicalObjectModel('star', stellar_params)
    >>> galaxy = AstrophysicalObjectModel('galaxy', galactic_params)
"""

from typing import Dict, Any
from .astrophysics.astrophysical_object_model import AstrophysicalObjectModel

# Re-export the main class for backward compatibility
__all__ = ["AstrophysicalObjectModel"]
