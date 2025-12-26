"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Stepwise power law analysis package for Level B.

This package implements stepwise tail analysis for the 7D phase field theory,
validating the theoretical prediction of discrete layered structure with
geometric decay instead of simple power law behavior.
"""

from .analyzer import LevelBPowerLawAnalyzer

__all__ = ["LevelBPowerLawAnalyzer"]
