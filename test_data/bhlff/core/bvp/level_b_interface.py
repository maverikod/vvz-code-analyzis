"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP level B interface implementation.

This module provides the main LevelBInterface class that coordinates
all Level B analysis operations for the 7D phase field theory.

Physical Meaning:
    Level B: Fundamental field properties including power law tails, nodes, and topological charge

Mathematical Foundation:
    Implements specific mathematical operations that work with BVP envelope data,
    transforming it according to level B requirements while maintaining BVP framework compliance.

Example:
    >>> level_b = LevelBInterface(bvp_core)
    >>> result = level_b.process_bvp_data(envelope)
"""

from .level_b_interface_facade import LevelBInterface
