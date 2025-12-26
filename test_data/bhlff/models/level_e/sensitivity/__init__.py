"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Sensitivity analysis module for Level E models.

This module provides tools for sensitivity analysis of defect systems,
including Sobol indices for parameter sensitivity and energy complexity analysis.

Physical Meaning:
    Sensitivity analysis quantifies how changes in input parameters
    affect the output of the system, providing insights into which
    parameters are most critical for system behavior.

Mathematical Foundation:
    Sensitivity analysis uses techniques such as Sobol indices to
    decompose the variance of the output into contributions from
    individual parameters and their interactions.
"""

from .sobol_analysis import SobolAnalyzer
from .energy_complexity_analysis import EnergyComplexityAnalyzer
