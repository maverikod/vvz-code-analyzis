"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for beating analyzer modules.

This module provides a unified interface for all beating analysis
functionality, delegating to specialized modules for different
aspects of beating analysis.
"""

from .beating_core import BeatingCoreAnalyzer
from .beating_validation import BeatingValidationAnalyzer

__all__ = ["BeatingCoreAnalyzer", "BeatingValidationAnalyzer"]
