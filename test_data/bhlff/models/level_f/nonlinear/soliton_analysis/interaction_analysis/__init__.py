"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton interaction analysis package.

This package provides comprehensive soliton interaction analysis
including stability, binding energy, and collective properties
using 7D BVP theory.

Physical Meaning:
    Analyzes soliton-soliton interactions in 7D phase field theory,
    including pairwise and multi-body interactions, stability
    criteria, and binding properties.

Example:
    >>> from .interaction_analyzer import SolitonInteractionAnalyzer
    >>> analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)
    >>> analysis = analyzer.analyze_interactions(multi_solitons)
"""

from .interaction_analyzer import SolitonInteractionAnalyzer
from .stability_analysis import SolitonStabilityAnalyzer
from .mode_analysis import SolitonModeAnalyzer
from .binding_analysis import SolitonBindingAnalyzer

__all__ = [
    "SolitonInteractionAnalyzer",
    "SolitonStabilityAnalyzer",
    "SolitonModeAnalyzer",
    "SolitonBindingAnalyzer",
]
