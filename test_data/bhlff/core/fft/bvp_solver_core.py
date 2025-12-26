"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for BVP solver core modules.

This module provides a unified interface for all BVP solver core
functionality, delegating to specialized modules for different
aspects of BVP solver core operations.
"""

from .bvp_solver_core_basic import BVPSolverCoreBasic
from .bvp_solver_core_advanced import BVPSolverCoreAdvanced

__all__ = ["BVPSolverCoreBasic", "BVPSolverCoreAdvanced"]
