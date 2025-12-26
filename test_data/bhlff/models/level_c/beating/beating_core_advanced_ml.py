"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning advanced beating core analysis facade for Level C.

This module provides a unified interface for machine learning-based beating analysis,
delegating to specialized modules for different aspects of ML analysis.
"""

from .ml import BeatingMLCore

# Alias for backward compatibility
BeatingCoreAdvancedML = BeatingMLCore

__all__ = ["BeatingMLCore", "BeatingCoreAdvancedML"]
