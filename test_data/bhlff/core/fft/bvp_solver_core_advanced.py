"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced BVP solver core facade for 7D envelope equation.

This module provides a unified interface for advanced BVP solving functionality,
delegating to specialized modules for different aspects of advanced solving.
"""

from .bvp_advanced import BVPAdvancedCore

# Alias for backward compatibility
BVPSolverCoreAdvanced = BVPAdvancedCore

__all__ = ["BVPAdvancedCore", "BVPSolverCoreAdvanced"]
