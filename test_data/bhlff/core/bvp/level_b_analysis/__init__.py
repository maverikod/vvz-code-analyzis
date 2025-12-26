"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level B analysis package for BVP interface.

This package provides analysis modules for Level B BVP interface,
including power law analysis, nodes detection, topological charge
computation, and zone separation analysis.

Physical Meaning:
    The Level B analysis package implements fundamental field properties
    analysis including power law tails, absence of spherical nodes,
    topological charge computation, and zone separation according to
    the 7D phase field theory.

Mathematical Foundation:
    Provides analysis tools for:
    - Power law decay A(r) ∝ r^(2β-3) in tail regions
    - Detection of spherical standing wave nodes
    - Topological charge computation using winding numbers
    - Zone separation analysis (core/transition/tail)

Example:
    >>> from .power_law_analyzer import PowerLawAnalyzer
    >>> from .nodes_analyzer import NodesAnalyzer
    >>> from .topological_charge_analyzer import TopologicalChargeAnalyzer
    >>> from .zone_separation_analyzer import ZoneSeparationAnalyzer
"""

from .power_law_analyzer import PowerLawAnalyzer
from .nodes_analyzer import NodesAnalyzer
from .topological_charge_analyzer import TopologicalChargeAnalyzer
from .zone_separation_analyzer import ZoneSeparationAnalyzer

__all__ = [
    "PowerLawAnalyzer",
    "NodesAnalyzer",
    "TopologicalChargeAnalyzer",
    "ZoneSeparationAnalyzer",
]
