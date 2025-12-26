"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological evolution models facade for 7D phase field theory.

This module provides a facade interface for cosmological evolution models,
delegating to specialized modules for different aspects of evolution.

Theoretical Background:
    The cosmological evolution module implements the time evolution
    of phase fields in expanding spacetime, where the phase field
    represents the fundamental field that drives structure formation.

Example:
    >>> from .evolution import CosmologicalEvolution
    >>> evolution = CosmologicalEvolution(initial_conditions, params)
    >>> results = evolution.evolve_cosmology(time_range)
"""

from typing import Dict, Any
from .evolution.cosmological_evolution import CosmologicalEvolution

# Re-export the main class for backward compatibility
__all__ = ["CosmologicalEvolution"]
