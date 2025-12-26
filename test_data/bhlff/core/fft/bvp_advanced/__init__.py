"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced BVP solver modules for 7D envelope equation.

This package provides advanced BVP solving functionality for the 7D envelope equation,
including optimization, preconditioning, and adaptive methods.
"""

from .bvp_advanced_core import BVPAdvancedCore
from .bvp_preconditioning import BVPPreconditioning
from .bvp_optimization import BVPOptimization
from .bvp_adaptive import BVPAdaptive

__all__ = ["BVPAdvancedCore", "BVPPreconditioning", "BVPOptimization", "BVPAdaptive"]
