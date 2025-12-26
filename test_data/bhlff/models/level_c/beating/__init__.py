"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Mode beating analysis package.

This package contains modules for mode beating analysis
for Level C test C4 in 7D phase field theory.

Physical Meaning:
    Implements comprehensive analysis of mode beating effects
    in the 7D phase field theory, including dual-mode excitation,
    beating patterns, and drift velocity analysis.

Example:
    >>> from bhlff.models.level_c.beating import ModeBeatingAnalysis
    >>> analyzer = ModeBeatingAnalysis(bvp_core)
    >>> results = analyzer.analyze_mode_beating(domain, beating_params)
"""

from .data_structures import DualModeSource, BeatingPattern
from .background_analysis import BackgroundBeatingAnalyzer
from .pinned_analysis import PinnedBeatingAnalyzer
from .theoretical_analysis import TheoreticalBeatingAnalyzer
