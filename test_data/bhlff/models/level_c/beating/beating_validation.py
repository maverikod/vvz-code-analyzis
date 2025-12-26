"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for beating validation modules.

This module provides a unified interface for all beating validation
functionality, delegating to specialized modules for different
aspects of beating validation.
"""

from .beating_validation_basic import BeatingValidationBasic
from .beating_validation_advanced import BeatingValidationAdvanced

__all__ = ["BeatingValidationBasic", "BeatingValidationAdvanced"]
