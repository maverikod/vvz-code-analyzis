"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Unified array interfaces for BHLFF framework.

This package provides unified interfaces for working with large 7D phase field
arrays that can be stored in memory or on disk transparently.
"""

from .field_array import FieldArray

__all__ = ["FieldArray"]

