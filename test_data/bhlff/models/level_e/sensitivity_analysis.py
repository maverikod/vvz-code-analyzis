"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Sensitivity analysis for Level E experiments using Sobol indices.

This module provides a facade for sensitivity analysis functionality
for Level E experiments in 7D phase field theory, ensuring proper
functionality of all sensitivity analysis components.

Theoretical Background:
    Sensitivity analysis quantifies the relative importance of different
    parameters in determining system behavior. Sobol indices provide
    a rigorous mathematical framework for ranking parameter influence
    on key observables.

Mathematical Foundation:
    Computes Sobol indices S_i = Var[E[Y|X_i]]/Var[Y] where Y is the
    output and X_i are the input parameters. Uses Latin Hypercube
    Sampling for efficient parameter space exploration.

Example:
    >>> analyzer = SensitivityAnalyzer(parameter_ranges)
    >>> results = analyzer.analyze_parameter_sensitivity(n_samples=1000)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import json
from scipy import stats
from scipy.optimize import minimize

from .sensitivity.sobol_analysis import SobolAnalyzer
from .sensitivity.energy_complexity_analysis import EnergyComplexityAnalyzer


class SensitivityAnalyzer:
    """
    Sobol sensitivity analysis for parameter ranking.

    Physical Meaning:
        Quantifies the relative importance of different parameters
        in determining the system behavior, providing insights into
        which parameters most strongly influence key observables.

    Mathematical Foundation:
        Computes Sobol indices S_i = Var[E[Y|X_i]]/Var[Y] where Y
        is the output and X_i are the input parameters.
    """

    def __init__(self, parameter_ranges: Dict[str, Tuple[float, float]]):
        """
        Initialize Sobol analyzer.

        Args:
            parameter_ranges: Dictionary mapping parameter names to (min, max) ranges
        """
        self.param_ranges = parameter_ranges
        self.param_names = list(parameter_ranges.keys())
        self.n_params = len(self.param_names)

        # Setup parameter indices
        self._param_indices = {name: i for i, name in enumerate(self.param_names)}

        # Initialize analysis components
        self.sobol_analyzer = SobolAnalyzer(parameter_ranges)
        self.energy_complexity_analyzer = EnergyComplexityAnalyzer()

    def generate_lhs_samples(self, n_samples: int) -> np.ndarray:
        """
        Generate Latin Hypercube samples.

        Physical Meaning:
            Creates efficient sampling of parameter space ensuring
            good coverage with minimal computational cost.

        Args:
            n_samples: Number of samples to generate

        Returns:
            Array of shape (n_samples, n_params) with parameter values
        """
        return self.sobol_analyzer.generate_lhs_samples(n_samples)

    def compute_sobol_indices(
        self, samples: np.ndarray, outputs: np.ndarray
    ) -> Dict[str, float]:
        """
        Compute Sobol sensitivity indices.

        Physical Meaning:
            Calculates first-order and total-order Sobol indices
            to rank parameter importance.

        Mathematical Foundation:
            S_i = Var[E[Y|X_i]]/Var[Y] (first-order)
            S_Ti = 1 - Var[E[Y|X_{-i}]]/Var[Y] (total-order)

        Args:
            samples: Parameter samples (n_samples, n_params)
            outputs: Corresponding output values (n_samples,)

        Returns:
            Dictionary with Sobol indices for each parameter
        """
        return self.sobol_analyzer.compute_sobol_indices(samples, outputs)

    def analyze_parameter_sensitivity(self, n_samples: int = 1000) -> Dict[str, Any]:
        """
        Perform complete sensitivity analysis.

        Physical Meaning:
            Executes full sensitivity analysis workflow including
            sampling, simulation, and index computation.

        Args:
            n_samples: Number of samples for analysis

        Returns:
            Complete sensitivity analysis results
        """
        # Generate parameter samples
        samples = self.generate_lhs_samples(n_samples)

        # Run simulations for each sample
        outputs = self.sobol_analyzer._run_simulations(samples)

        # Compute Sobol indices
        sobol_indices = self.compute_sobol_indices(samples, outputs)

        # Rank parameters by importance
        ranking = self.sobol_analyzer._rank_parameters(sobol_indices)

        # Compute stability metrics
        stability_metrics = self.sobol_analyzer._compute_stability_metrics(
            sobol_indices
        )

        return {
            "samples": samples,
            "outputs": outputs,
            "sobol_indices": sobol_indices,
            "parameter_ranking": ranking,
            "stability_metrics": stability_metrics,
            "n_samples": n_samples,
            "parameter_ranges": self.param_ranges,
        }

    def analyze_energy_complexity_correlation(
        self, samples: np.ndarray, outputs: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze correlation between energy and complexity.

        Physical Meaning:
            Investigates the "energy = complexity" thesis by analyzing
            the correlation between particle energy and field complexity
            in the 7D phase field theory.
        """
        return self.energy_complexity_analyzer.analyze_energy_complexity_correlation(
            samples, outputs
        )

    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save sensitivity analysis results to file.

        Args:
            results: Analysis results dictionary
            filename: Output filename
        """
        # Convert numpy arrays to lists for JSON serialization
        serializable_results = self._make_serializable(results)

        with open(filename, "w") as f:
            json.dump(serializable_results, f, indent=2)

    def _make_serializable(self, obj: Any) -> Any:
        """Convert numpy arrays to lists for JSON serialization."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        else:
            return obj
