"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law core analysis modules for BVP framework.

This package provides core power law analysis functionality for the BVP framework,
including basic power law fitting and tail region analysis.
"""

from .power_law_core_main import PowerLawCoreMain
from .power_law_tail_analysis import PowerLawTailAnalysis
from .power_law_region_analysis import PowerLawRegionAnalysis
from .power_law_fitting import PowerLawFitting

__all__ = [
    "PowerLawCoreMain",
    "PowerLawTailAnalysis",
    "PowerLawRegionAnalysis",
    "PowerLawFitting",
]
