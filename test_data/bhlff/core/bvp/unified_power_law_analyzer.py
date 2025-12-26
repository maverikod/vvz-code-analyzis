"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for power law analysis modules.

This module provides a unified interface for all power law analysis
functionality, delegating to specialized modules for different
aspects of power law analysis.
"""

from .power_law_core import PowerLawCore
from .power_law_analysis import PowerLawAnalysis

# Alias for backward compatibility
UnifiedPowerLawAnalyzer = PowerLawAnalysis

__all__ = ["PowerLawCore", "PowerLawAnalysis", "UnifiedPowerLawAnalyzer"]
