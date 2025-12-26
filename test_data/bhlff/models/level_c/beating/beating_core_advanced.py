"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for advanced beating core modules.

This module provides a unified interface for all advanced beating core
functionality, delegating to specialized modules for different
aspects of advanced beating core operations.
"""

from .beating_core_advanced_basic import BeatingCoreAdvancedBasic
from .beating_core_advanced_ml import BeatingCoreAdvancedML

__all__ = ["BeatingCoreAdvancedBasic", "BeatingCoreAdvancedML"]
