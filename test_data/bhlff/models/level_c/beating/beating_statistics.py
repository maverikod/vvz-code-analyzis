"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating statistics analysis utilities for Level C.

This module provides statistical analysis functions for beating
analysis in the 7D phase field.
"""

from .beating_correlation import BeatingCorrelationAnalyzer
from .beating_patterns import BeatingPatternDetector

__all__ = ["BeatingCorrelationAnalyzer", "BeatingPatternDetector"]
