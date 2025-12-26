"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level D models for multimode superposition and field projections.

This module implements Level D models for the 7D phase field theory, including
multimode superposition analysis, field projections onto different interaction
windows (electromagnetic, strong, weak), and phase streamline analysis.

Physical Meaning:
    Level D represents the multimode superposition and field projection level
    of the 7D phase field theory, where all observed particles emerge as
    envelope functions of a high-frequency carrier field through different
    frequency-amplitude windows.

Mathematical Foundation:
    - Multimode superposition: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
    - Field projections: EM, strong, and weak interactions as different
      frequency windows of the unified phase field
    - Phase streamlines: Analysis of phase gradient flow patterns

Example:
    >>> from bhlff.models.level_d import LevelDModels
    >>> models = LevelDModels(domain, parameters)
    >>> results = models.analyze_multimode_field(field)
"""

from .level_d_models import LevelDModels
from .superposition import MultiModeModel, SuperpositionAnalyzer
from .projections import FieldProjection, ProjectionAnalyzer
from .streamlines import StreamlineAnalyzer
from .bvp_integration import LevelDBVPIntegration

__all__ = [
    "LevelDModels",
    "MultiModeModel",
    "SuperpositionAnalyzer",
    "FieldProjection",
    "ProjectionAnalyzer",
    "StreamlineAnalyzer",
    "LevelDBVPIntegration",
]
