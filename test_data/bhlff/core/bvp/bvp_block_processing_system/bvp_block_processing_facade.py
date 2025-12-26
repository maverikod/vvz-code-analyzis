"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for BVP block processing system.

This module composes the base implementation and mixins into the
BVPBlockProcessingSystem facade that is used by the rest of the codebase.
"""

from .bvp_block_processing_base import BVPBlockProcessingBase
from .bvp_block_processing_solver import BVPBlockProcessingSolverMixin
from .bvp_block_processing_quench import BVPBlockProcessingQuenchMixin
from .bvp_block_processing_impedance import BVPBlockProcessingImpedanceMixin
from .bvp_block_processing_management import BVPBlockProcessingManagementMixin


class BVPBlockProcessingSystem(
    BVPBlockProcessingBase,
    BVPBlockProcessingSolverMixin,
    BVPBlockProcessingQuenchMixin,
    BVPBlockProcessingImpedanceMixin,
    BVPBlockProcessingManagementMixin,
):
    """
    Facade class composing all BVP block processing functionality.
    
    Physical Meaning:
        Provides the high-level interface for solving, analysing, and managing
        block processed 7D BVP envelopes with optional GPU acceleration.
    """

    pass
