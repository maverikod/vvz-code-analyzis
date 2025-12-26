"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base module for BHLFF models.

This module contains abstract base classes and interfaces for all
model components in the BHLFF framework.

Physical Meaning:
    Base classes provide the fundamental interfaces and common
    functionality for all model components in the 7D phase field
    theory implementation.

Mathematical Foundation:
    Base classes implement common mathematical operations and interfaces
    required for analyzing different levels of the phase field theory.
"""

from .abstract_models import AbstractLevelModels
from .abstract_model import AbstractModel

__all__ = [
    "AbstractLevelModels",
    "AbstractModel",
]
