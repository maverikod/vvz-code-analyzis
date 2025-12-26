"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Discretization effects analysis facade for Level E experiments.

This module provides the main DiscretizationAnalyzer class that coordinates
comprehensive analysis of discretization and finite-size effects in the 7D phase field theory.

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
    >>> analyzer = DiscretizationAnalyzer(reference_config)
    >>> results = analyzer.analyze_grid_convergence(grid_sizes)
"""

from typing import Dict, Any, List
from .discretization import DiscretizationAnalyzer as CoreDiscretizationAnalyzer


class DiscretizationAnalyzer:
    """
    Discretization effects analysis facade for system stability.

    Physical Meaning:
        Investigates how numerical discretization and finite
        domain size affect the accuracy and reliability of
        computational results.
    """

    def __init__(self, reference_config: Dict[str, Any]):
        """
        Initialize discretization analyzer.

        Args:
            reference_config: Reference configuration for comparison
        """
        self.reference_config = reference_config
        self.core_analyzer = CoreDiscretizationAnalyzer(reference_config)

    def analyze_grid_convergence(self, grid_sizes: List[int]) -> Dict[str, Any]:
        """
        Analyze convergence with grid refinement.

        Physical Meaning:
            Investigates how results change as the computational
            grid is refined, establishing convergence rates and
            optimal grid sizes.

        Mathematical Foundation:
            Computes convergence rate: p = log(|e_h1|/|e_h2|)/log(h1/h2)
            where e_h is the error at grid spacing h.

        Args:
            grid_sizes: List of grid sizes to test

        Returns:
            Convergence analysis results
        """
        return self.core_analyzer.analyze_grid_convergence(grid_sizes)

    def analyze_domain_size_effects(self, domain_sizes: List[float]) -> Dict[str, Any]:
        """
        Analyze effects of finite domain size.

        Physical Meaning:
            Investigates how the finite computational domain
            affects results, particularly for long-range
            interactions and boundary effects.

        Args:
            domain_sizes: List of domain sizes to test

        Returns:
            Domain size analysis results
        """
        return self.core_analyzer.analyze_domain_size_effects(domain_sizes)

    def analyze_time_step_stability(self, time_steps: List[float]) -> Dict[str, Any]:
        """
        Analyze stability with respect to time step.

        Physical Meaning:
            Investigates numerical stability of time integration
            schemes and optimal time step selection.

        Args:
            time_steps: List of time steps to test

        Returns:
            Time step stability analysis
        """
        return self.core_analyzer.analyze_time_step_stability(time_steps)

    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save discretization analysis results to file.

        Args:
            results: Analysis results dictionary
            filename: Output filename
        """
        return self.core_analyzer.save_results(results, filename)
