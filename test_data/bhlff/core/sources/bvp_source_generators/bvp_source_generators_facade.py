"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for BVP source generators.

This module provides the main BVPSourceGenerators facade class that
coordinates all BVP source generators components.
"""

from .bvp_source_generators_base import BVPSourceGeneratorsBase
from .bvp_source_generators_basic import BVPSourceGeneratorsBasicMixin
from .bvp_source_generators_substrate import BVPSourceGeneratorsSubstrateMixin
from .bvp_source_generators_defects import BVPSourceGeneratorsDefectsMixin
from .bvp_source_generators_helpers import BVPSourceGeneratorsHelpersMixin


class BVPSourceGenerators(
    BVPSourceGeneratorsBase,
    BVPSourceGeneratorsBasicMixin,
    BVPSourceGeneratorsSubstrateMixin,
    BVPSourceGeneratorsDefectsMixin,
    BVPSourceGeneratorsHelpersMixin
):
    """
    Facade class for BVP source generators with all mixins.
    
    Physical Meaning:
        Generates different types of base sources that can be modulated
        by the BVP framework for phase field evolution.
    """
    pass

