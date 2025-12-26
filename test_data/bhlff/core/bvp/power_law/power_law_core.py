"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core power law analysis facade for BVP framework.

This module provides a unified interface for core power law analysis functionality,
delegating to specialized modules for different aspects of power law analysis.
"""

from .power_law_core.power_law_core_facade import PowerLawCore

__all__ = ["PowerLawCore"]
