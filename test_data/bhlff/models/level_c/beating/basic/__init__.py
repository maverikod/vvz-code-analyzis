"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic beating analysis package.

This package contains modules for basic beating analysis
for Level C in 7D phase field theory.

Physical Meaning:
    Implements basic beating analysis functionality for analyzing
    mode beating in the 7D phase field according to the theoretical framework.

Example:
    >>> from bhlff.models.level_c.beating.basic import CoreBeatingAnalyzer
    >>> analyzer = CoreBeatingAnalyzer(bvp_core)
    >>> results = analyzer.analyze_beating_comprehensive(envelope)
"""

from .core_analysis import CoreBeatingAnalyzer
from .statistical_analysis import StatisticalBeatingAnalyzer
from .optimization import BeatingOptimizer
from .comparison import BeatingComparator
