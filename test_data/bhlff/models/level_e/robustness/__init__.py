"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Robustness testing package for Level E experiments.

This package provides comprehensive robustness testing for the 7D phase
field theory, investigating system stability under various perturbations
including noise, parameter uncertainties, and geometry variations.

Theoretical Background:
    Robustness testing investigates how the system responds to external
    perturbations, noise, and parameter uncertainties to establish stability
    boundaries and failure modes. This is crucial for understanding the practical
    applicability of the 7D theory.

Mathematical Foundation:
    Tests system response to perturbations of the form:
    - BVP-modulation noise: a(x) → a(x) + ε·N(0,1)
    - Parameter uncertainties: p → p + δp
    - Geometry perturbations: domain deformation

Example:
    >>> from .robustness_tester import RobustnessTester
    >>> tester = RobustnessTester(base_config)
    >>> results = tester.test_noise_robustness(noise_levels)
"""

from .robustness_tester import RobustnessTester
from .noise_testing import NoiseRobustnessTester
from .parameter_testing import ParameterRobustnessTester
from .geometry_testing import GeometryRobustnessTester

__all__ = [
    "RobustnessTester",
    "NoiseRobustnessTester",
    "ParameterRobustnessTester",
    "GeometryRobustnessTester",
]
