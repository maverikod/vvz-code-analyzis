"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

ABCD model package for resonator chains in Level C.

This package implements the ABCD transmission matrix method with spectral
analysis for cascaded resonators in the 7D phase field theory.
"""

from .data_structures import ResonatorLayer, SystemMode
from .spectral_analysis import ABCDSpectralAnalyzer
from .transmission_core import ABCDTransmissionCore
from .vectorized_ops import ABCDVectorizedOps
from .block_processing import ABCDBlockProcessing

__all__ = [
    "ResonatorLayer",
    "SystemMode",
    "ABCDSpectralAnalyzer",
    "ABCDTransmissionCore",
    "ABCDVectorizedOps",
    "ABCDBlockProcessing",
]

