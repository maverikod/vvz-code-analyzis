"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Large-scale structure models facade for 7D phase field theory.

This module provides a facade interface for large-scale structure models,
delegating to specialized modules for different aspects of structure formation.

Theoretical Background:
    Large-scale structure formation is driven by the evolution of
    phase field configurations on cosmological scales, where
    topological defects and phase coherence give rise to observable
    structures.

Example:
    >>> from .structure import LargeScaleStructureModel
    >>> structure = LargeScaleStructureModel(initial_fluctuations, params)
    >>> evolution = structure.evolve_structure(time_range)
"""

from typing import Dict, Any
from .structure.large_scale_structure_model import LargeScaleStructureModel

# Re-export the main class for backward compatibility
__all__ = ["LargeScaleStructureModel"]
