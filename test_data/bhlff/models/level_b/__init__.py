"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level B models for fundamental properties analysis.

This package implements Level B operations for the 7D phase field theory,
providing analysis of fundamental properties including power law tails,
node analysis, topological charge, and zone separation.

Physical Meaning:
    Level B represents the analysis of fundamental properties of the
    BVP field including statistical properties, topological characteristics,
    and spatial pattern analysis.

Mathematical Foundation:
    Implements comprehensive analysis of BVP field properties including
    power law analysis, topological analysis, and spatial pattern
    recognition for understanding fundamental field behavior.

Example:
    >>> from bhlff.models.level_b import LevelBPowerLawAnalyzer
    >>> analyzer = LevelBPowerLawAnalyzer(bvp_core)
    >>> results = analyzer.analyze_power_laws(envelope)
"""

from .power_law_analyzer import LevelBPowerLawAnalyzer
from .node_analyzer import LevelBNodeAnalyzer
from .zone_analyzer import LevelBZoneAnalyzer
from .visualization import LevelBVisualizer

__all__ = [
    "LevelBPowerLawAnalyzer",
    "LevelBNodeAnalyzer",
    "LevelBZoneAnalyzer",
    "LevelBVisualizer",
]
