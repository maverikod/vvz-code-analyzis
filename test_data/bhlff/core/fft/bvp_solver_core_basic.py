"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic BVP solver core facade for 7D envelope equation.

This module provides a unified interface for basic BVP solving functionality,
delegating to specialized modules for different aspects of basic solving.
"""

from .bvp_basic import BVBBasicCore

# Alias for backward compatibility
BVPSolverCoreBasic = BVBBasicCore

__all__ = ["BVBBasicCore", "BVPSolverCoreBasic"]
