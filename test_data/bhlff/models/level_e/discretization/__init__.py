"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Discretization effects analysis package for Level E experiments.

This package provides comprehensive analysis of discretization and
finite-size effects in the 7D phase field theory, investigating
how numerical discretization and finite domain size affect accuracy
and reliability of computational results.

Theoretical Background:
    Discretization effects analysis investigates how numerical
    discretization and finite domain size affect the accuracy and
    reliability of computational results. This is crucial for
    establishing convergence and optimal computational parameters.

Mathematical Foundation:
    Analyzes convergence rates: p = log(|e_h1|/|e_h2|)/log(h1/h2)
    where e_h is the error at grid spacing h. Investigates effects
    of finite domain size on long-range interactions.

Example:
    >>> from .discretization_analyzer import DiscretizationAnalyzer
    >>> analyzer = DiscretizationAnalyzer(reference_config)
    >>> results = analyzer.analyze_grid_convergence(grid_sizes)
"""

from .discretization_analyzer import DiscretizationAnalyzer
from .grid_convergence import GridConvergenceAnalyzer
from .domain_effects import DomainEffectsAnalyzer
from .time_stability import TimeStabilityAnalyzer

__all__ = [
    "DiscretizationAnalyzer",
    "GridConvergenceAnalyzer",
    "DomainEffectsAnalyzer",
    "TimeStabilityAnalyzer",
]
