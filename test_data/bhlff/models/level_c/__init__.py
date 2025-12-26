"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level C: Boundaries and Cells module for BVP framework.

This module implements Level C analysis focusing on boundaries and cells
in the 7D phase field theory, including boundary effects, resonators,
memory systems, and mode beating analysis.

Physical Meaning:
    Level C analyzes the boundary effects and cellular structures that
    emerge in the 7D phase field, including:
    - Boundary effects and their influence on field dynamics
    - Resonator structures and their frequency characteristics
    - Memory systems and information storage mechanisms
    - Mode beating and interference patterns

Mathematical Foundation:
    Implements analysis of:
    - Boundary conditions and their effects on field evolution
    - Resonator equations and frequency response
    - Memory kernel analysis and information retention
    - Mode coupling and beating frequency analysis

Example:
    >>> from bhlff.models.level_c import LevelCAnalyzer
    >>> analyzer = LevelCAnalyzer(bvp_core)
    >>> results = analyzer.analyze_boundaries_and_cells(envelope)
"""

from .boundaries import BoundaryAnalyzer
from .boundary_analysis import BoundaryAnalysis
from .abcd_model import ABCDModel
from .abcd import ResonatorLayer, SystemMode
from .quench_memory_analysis import QuenchMemoryAnalysis, MemoryParameters, QuenchEvent
from .mode_beating_analysis import ModeBeatingAnalysis, DualModeSource, BeatingPattern
from .level_c_integration import LevelCIntegration, LevelCResults, TestConfiguration

__all__ = [
    "BoundaryAnalyzer",
    "BoundaryAnalysis",
    "ABCDModel",
    "ResonatorLayer",
    "SystemMode",
    "QuenchMemoryAnalysis",
    "MemoryParameters",
    "QuenchEvent",
    "ModeBeatingAnalysis",
    "DualModeSource",
    "BeatingPattern",
    "LevelCIntegration",
    "LevelCResults",
    "TestConfiguration",
]
