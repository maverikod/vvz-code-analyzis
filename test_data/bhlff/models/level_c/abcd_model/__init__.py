"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ABCD model package for resonator chains in Level C.

This package implements the ABCD transmission matrix method with spectral
analysis for cascaded resonators in the 7D phase field theory, split into
logical modules for maintainability.
"""

from .abcd_model_package import ABCDModel

# Import data structures from abcd package
from ..abcd import ResonatorLayer, SystemMode

__all__ = [
    "ABCDModel",
    "ResonatorLayer",
    "SystemMode",
]
