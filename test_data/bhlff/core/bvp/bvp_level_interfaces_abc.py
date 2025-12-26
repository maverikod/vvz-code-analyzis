"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP level interfaces for levels A-C implementation.

This module provides integration interfaces for levels A-C of the 7D phase field theory,
ensuring that BVP serves as the central backbone for validation, scaling, fundamental
properties, boundaries, and resonator analysis.

Physical Meaning:
    Level A: Validation and scaling operations for BVP framework compliance
    Level B: Fundamental field properties including power law tails, nodes, and topological charge
    Level C: Boundary effects, resonator structures, quench memory, and mode beating

Mathematical Foundation:
    Each level implements specific mathematical operations that work with BVP envelope data,
    transforming it according to level-specific requirements while maintaining BVP framework compliance.

Example:
    >>> level_a = LevelAInterface(bvp_core)
    >>> level_b = LevelBInterface(bvp_core)
    >>> level_c = LevelCInterface(bvp_core)
"""

from .level_a_interface import LevelAInterface
from .level_b_interface import LevelBInterface
from .level_c_interface import LevelCInterface
