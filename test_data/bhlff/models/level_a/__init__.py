"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level A models for BVP framework validation and scaling.

This package implements Level A operations for the 7D phase field theory,
providing validation, scaling, and nondimensionalization capabilities
integrated with the BVP framework.

Physical Meaning:
    Level A represents the foundational validation and scaling operations
    that ensure BVP framework compliance and proper dimensional analysis
    for the 7D phase field theory.

Mathematical Foundation:
    Implements validation tests and scaling operations that work with
    BVP envelope data to ensure physical correctness and dimensional
    consistency across all system components.

Example:
    >>> from bhlff.models.level_a import LevelAValidator
    >>> validator = LevelAValidator(bvp_core)
    >>> results = validator.validate_bvp_framework()
"""

from .validation import LevelAValidator

__all__ = ["LevelAValidator"]
