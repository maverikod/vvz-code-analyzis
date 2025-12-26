"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic advanced beating validation facade for Level C.

This module provides a unified interface for basic advanced beating validation,
delegating to specialized modules for different aspects of validation.
"""

from .validation import BeatingValidationCore

# Alias for backward compatibility
BeatingValidationAdvancedBasic = BeatingValidationCore

__all__ = ["BeatingValidationCore", "BeatingValidationAdvancedBasic"]
