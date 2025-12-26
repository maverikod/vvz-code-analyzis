"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic advanced beating core analysis facade for Level C.

This module provides a unified interface for basic advanced beating analysis,
delegating to specialized modules for different aspects of analysis.
"""

from .basic import BeatingBasicCore

# Alias for backward compatibility
BeatingCoreAdvancedBasic = BeatingBasicCore

__all__ = ["BeatingBasicCore", "BeatingCoreAdvancedBasic"]
