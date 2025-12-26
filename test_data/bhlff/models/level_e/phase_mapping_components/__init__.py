"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase mapping components module for Level E models.

This module provides components for analyzing phase mapping in defect systems,
including regime classification, boundary analysis, and resonance analysis.

Physical Meaning:
    Phase mapping components analyze the spatial distribution of phase
    configurations in defect systems, identifying different regimes of
    behavior and characterizing boundary effects and resonances.

Mathematical Foundation:
    Phase mapping involves the analysis of phase field configurations
    and their topological properties, including classification of
    different regimes and identification of resonant modes.
"""

from .regime_classification import RegimeClassifier
from .boundary_analysis import BoundaryAnalyzer
from .resonance_analysis import ResonanceAnalyzer
