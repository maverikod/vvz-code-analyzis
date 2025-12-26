"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Shim file for backward compatibility with stepwise package refactoring.

This file provides backward compatibility by re-exporting LevelBPowerLawAnalyzer
from the new stepwise package structure.
"""

from .stepwise import LevelBPowerLawAnalyzer  # noqa: F401

__all__ = ["LevelBPowerLawAnalyzer"]
