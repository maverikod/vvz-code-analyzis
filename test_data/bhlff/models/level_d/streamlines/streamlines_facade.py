"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for streamline analyzer.

This module provides the main StreamlineAnalyzer facade class that
coordinates all streamline analyzer components.
"""

from .streamlines_base import StreamlineAnalyzerBase
from .streamlines_analysis import StreamlineAnalyzerAnalysisMixin


class StreamlineAnalyzer(
    StreamlineAnalyzerBase,
    StreamlineAnalyzerAnalysisMixin
):
    """
    Facade class for streamline analyzer with all mixins.
    
    Physical Meaning:
        Analyzes phase gradient flow patterns to understand
        the topological structure of phase flow around
        defects and singularities.
    """
    pass

