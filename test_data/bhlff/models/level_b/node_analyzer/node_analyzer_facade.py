"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for node analyzer.

This module provides the main LevelBNodeAnalyzer facade class that
coordinates all node analyzer components.
"""

from .node_analyzer_base import LevelBNodeAnalyzerBase
from .node_analyzer_nodes import LevelBNodeAnalyzerNodesMixin
from .node_analyzer_topology import LevelBNodeAnalyzerTopologyMixin
from .node_analyzer_radial import LevelBNodeAnalyzerRadialMixin
from .node_analyzer_stepwise import LevelBNodeAnalyzerStepwiseMixin
from .node_analyzer_visualization import LevelBNodeAnalyzerVisualizationMixin


class LevelBNodeAnalyzer(
    LevelBNodeAnalyzerBase,
    LevelBNodeAnalyzerNodesMixin,
    LevelBNodeAnalyzerTopologyMixin,
    LevelBNodeAnalyzerRadialMixin,
    LevelBNodeAnalyzerStepwiseMixin,
    LevelBNodeAnalyzerVisualizationMixin
):
    """
    Facade class for node analyzer with all mixins.
    
    Physical Meaning:
        Analyzes the absence of spherical standing nodes in homogeneous
        medium and computes topological charge for defect stability.
    """
    pass

