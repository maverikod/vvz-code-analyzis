"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for beating core modules.

This module provides a unified interface for all beating core
functionality, delegating to specialized modules for different
aspects of beating core operations.
"""

from .beating_core_basic import BeatingCoreBasic
from .beating_core_advanced import BeatingCoreAdvanced

__all__ = ["BeatingCoreBasic", "BeatingCoreAdvanced"]
