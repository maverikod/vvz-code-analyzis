"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field projections facade.

This module provides a unified interface for field projections functionality.
"""

from .projections.projections_facade import FieldProjection
from .projections.projections_analyzer import ProjectionAnalyzer

__all__ = ["FieldProjection", "ProjectionAnalyzer"]
