"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Level Integration package.

This package provides BVP integration interfaces for all model levels A-G,
enabling BVP-centric analysis and validation across the entire 7D phase field
theory framework.

Physical Meaning:
    Each level integration class provides BVP-specific analysis methods
    that replace classical approaches with BVP-centric methodologies,
    ensuring that all model levels operate within the BVP framework.

Mathematical Foundation:
    BVP integration ensures that all model levels:
    - Use BVP envelope equations as the fundamental solver
    - Apply BVP postulates for validation
    - Detect quench events for regime transitions
    - Maintain U(1)³ phase structure throughout

Example:
    >>> from bhlff.core.bvp.level_integration import LevelABVPIntegration
    >>> level_a = LevelABVPIntegration(bvp_core)
    >>> results = level_a.validate_bvp_solvers()
"""

from .level_a_bvp_integration import LevelABVPIntegration
from .level_b_bvp_integration import LevelBBVPIntegration
from .level_c_bvp_integration import LevelCBVPIntegration
from .level_d_bvp_integration import LevelDBVPIntegration
from .level_e_bvp_integration import LevelEBVPIntegration
from .level_f_bvp_integration import LevelFBVPIntegration
from .level_g_bvp_integration import LevelGBVPIntegration

__all__ = [
    "LevelABVPIntegration",
    "LevelBBVPIntegration",
    "LevelCBVPIntegration",
    "LevelDBVPIntegration",
    "LevelEBVPIntegration",
    "LevelFBVPIntegration",
    "LevelGBVPIntegration",
]
