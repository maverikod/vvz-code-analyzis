"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radial profile computation package.

This package provides radial profile computation with CUDA acceleration,
split into modules for maintainability.
"""

from .radial_profile_facade import RadialProfileComputer

__all__ = ["RadialProfileComputer"]

