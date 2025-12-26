"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis package for phase mapping.

This package implements comprehensive boundary analysis functionality
for identifying transition boundaries between different system
behavior regimes using 7D BVP theory.

Theoretical Background:
    Boundary analysis identifies transition points between different
    regimes in parameter space, revealing the structure of the phase
    diagram through 7D phase field analysis.

Example:
    >>> from bhlff.models.level_e.phase_mapping_components.boundary_analysis import BoundaryAnalyzer
    >>> analyzer = BoundaryAnalyzer()
    >>> boundaries = analyzer.analyze_regime_boundaries(parameter_grid, classifications)
"""

from .boundary_analyzer import BoundaryAnalyzer
from .phase_coherence_analysis import PhaseCoherenceAnalyzer
from .topological_analysis import TopologicalAnalyzer
from .energy_landscape_analysis import EnergyLandscapeAnalyzer

__all__ = [
    "BoundaryAnalyzer",
    "PhaseCoherenceAnalyzer",
    "TopologicalAnalyzer",
    "EnergyLandscapeAnalyzer",
]
