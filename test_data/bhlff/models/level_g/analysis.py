"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological analysis tools facade for 7D phase field theory.

This module provides a facade interface for cosmological analysis tools,
delegating to specialized modules for different aspects of analysis.

Theoretical Background:
    The cosmological analysis module provides tools for analyzing
    the results of cosmological evolution, including structure
    formation metrics and parameter evolution.

Example:
    >>> from .analysis import CosmologicalAnalysis
    >>> analysis = CosmologicalAnalysis(evolution_results)
    >>> structure_analysis = analysis.analyze_structure_formation()
"""

from typing import Dict, Any
from .analysis.cosmological_analysis import CosmologicalAnalysis

# Re-export the main class for backward compatibility
__all__ = ["CosmologicalAnalysis"]
