"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological models facade for 7D phase field theory.

This module provides a facade interface for cosmological models,
delegating to specialized modules for different aspects of cosmology.

Theoretical Background:
    Gravity-like effects emerge from the curvature of the VBP envelope
    in the 7D phase field theory. There is no spacetime curvature here;
    instead, an effective metric g_eff[Θ] is derived from envelope
    invariants and phase dynamics.

Example:
    >>> from .cosmology import CosmologicalModel
    >>> cosmology = CosmologicalModel(initial_conditions, params)
    >>> evolution = cosmology.evolve_universe([0, 13.8])
"""

from typing import Dict, Any
from .cosmology.cosmological_model import CosmologicalModel
from .cosmology.envelope_effective_metric import EnvelopeEffectiveMetric

# Re-export the main classes for backward compatibility
__all__ = ["CosmologicalModel", "EnvelopeEffectiveMetric"]
