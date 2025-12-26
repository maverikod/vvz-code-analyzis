"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating validation modules for Level C.

This package provides validation functionality for beating analysis
in the 7D phase field.
"""

from .beating_validation_core import BeatingValidationCore
from .beating_validation_statistics import BeatingValidationStatistics
from .beating_validation_comparison import BeatingValidationComparison

__all__ = [
    "BeatingValidationCore",
    "BeatingValidationStatistics",
    "BeatingValidationComparison",
]
