"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic beating validation modules for Level C.

This package provides basic validation functionality for beating
analysis in the 7D phase field.
"""

from .beating_validation_frequencies import BeatingValidationFrequencies
from .beating_validation_patterns import BeatingValidationPatterns

__all__ = ["BeatingValidationFrequencies", "BeatingValidationPatterns"]
