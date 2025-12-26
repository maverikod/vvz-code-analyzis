"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for field projections.

This module provides the main FieldProjection facade class that
coordinates all field projection components.
"""

from .projections_base import FieldProjectionBase
from .projections_projections import FieldProjectionProjectionsMixin
from .projections_analyzer import ProjectionAnalyzer


class FieldProjection(
    FieldProjectionBase,
    FieldProjectionProjectionsMixin
):
    """
    Facade class for field projection onto different interaction windows.
    
    Physical Meaning:
        Projects the unified phase field onto different frequency
        windows corresponding to electromagnetic, strong, and weak
        interactions as envelope functions.
    """
    pass

