"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Legacy BVP postulates module - DEPRECATED.

This module is deprecated. Use the new modular structure:
- bhlff.core.bvp.postulates.BVPPostulates7D
- Individual postulate modules in bhlff.core.bvp.postulates.*

The postulates have been refactored into separate modules following
the 1 class = 1 file principle and size limits.

Physical Meaning:
    This legacy module contained all 9 BVP postulates in a single file,
    which violated project standards. The postulates have been moved
    to individual modules for better maintainability.

Example:
    # OLD (deprecated):
    # from bhlff.core.bvp.bvp_postulates_7d import BVPPostulates7D

    # NEW (recommended):
    from bhlff.core.bvp.postulates import BVPPostulates7D
"""

# Import from the new modular structure
from .postulates import BVPPostulates7D
from .postulates import (
    BVPPostulate1_CarrierPrimacy,
    BVPPostulate2_ScaleSeparation,
    BVPPostulate3_BVPRigidity,
    BVPPostulate4_U1PhaseStructure,
    BVPPostulate5_Quenches,
    BVPPostulate6_TailResonatorness,
    BVPPostulate7_TransitionZone,
    BVPPostulate8_CoreRenormalization,
    BVPPostulate9_PowerBalance,
)

# Re-export for backward compatibility
__all__ = [
    "BVPPostulates7D",
    "BVPPostulate1_CarrierPrimacy",
    "BVPPostulate2_ScaleSeparation",
    "BVPPostulate3_BVPRigidity",
    "BVPPostulate4_U1PhaseStructure",
    "BVPPostulate5_Quenches",
    "BVPPostulate6_TailResonatorness",
    "BVPPostulate7_TransitionZone",
    "BVPPostulate8_CoreRenormalization",
    "BVPPostulate9_PowerBalance",
]
