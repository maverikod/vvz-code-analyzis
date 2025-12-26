"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for power law core analyzer.

This module provides the main PowerLawCore facade class that
coordinates all power law core analysis components.
"""

from .power_law_core_base import PowerLawCoreBase
from .power_law_core_regions import PowerLawCoreRegionsMixin
from .power_law_core_fitting import PowerLawCoreFittingMixin
from .power_law_core_quality import PowerLawCoreQualityMixin


class PowerLawCore(
    PowerLawCoreBase,
    PowerLawCoreRegionsMixin,
    PowerLawCoreFittingMixin,
    PowerLawCoreQualityMixin
):
    """
    Facade class for core power law analyzer with all mixins.
    
    Physical Meaning:
        Provides core analysis of power law behavior in BVP
        envelope fields, coordinating specialized analysis modules.
    """
    pass

