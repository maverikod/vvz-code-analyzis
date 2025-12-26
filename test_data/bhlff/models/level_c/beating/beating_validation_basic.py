"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic beating validation facade for Level C.

This module provides a unified interface for basic beating validation functionality,
delegating to specialized modules for different aspects of validation.
"""

from .validation_basic import BeatingValidationBasicMain

# Alias for backward compatibility
BeatingValidationBasic = BeatingValidationBasicMain

__all__ = ["BeatingValidationBasicMain", "BeatingValidationBasic"]
