"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Collective modes finding package.

This package provides collective modes finding functionality for multi-particle systems
in Level F of 7D phase field theory, split into modules for maintainability.
"""

from .collective_modes_finding_facade import CollectiveModesFinder

__all__ = ["CollectiveModesFinder"]

