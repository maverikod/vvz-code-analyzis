"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for beating analysis modules.

This module provides a unified interface to all beating analysis components,
importing from the modular structure for better maintainability.
"""

# Import all classes from the modular structure
from .beating.beating_analyzer import BeatingAnalyzer
from .beating.beating_utilities import BeatingUtilities, BeatingVisualizer

# Re-export all classes for backward compatibility
__all__ = ["BeatingAnalyzer", "BeatingUtilities", "BeatingVisualizer"]
