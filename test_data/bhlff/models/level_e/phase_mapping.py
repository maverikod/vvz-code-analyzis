"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase mapping for Level E experiments.

This module provides a facade for phase mapping functionality
for Level E experiments in 7D phase field theory, ensuring proper
functionality of all phase mapping components.

Theoretical Background:
    Phase mapping investigates how different parameter combinations
    lead to qualitatively different system behaviors: power law tails,
    resonator structures, frozen configurations, and leaky modes.
    This provides a complete classification of system behavior.

Mathematical Foundation:
    Classifies regimes based on key observables:
    - PL (Power Law): Steep power law tails with exponent p = 2β - 3
    - R (Resonator): High-Q resonator structures
    - FRZ (Frozen): Frozen configurations with minimal dynamics
    - LEAK (Leaky): Energy leakage modes

Example:
    >>> mapper = PhaseMapper(config)
    >>> phase_map = mapper.map_phases()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import json

from .phase_mapping_components.regime_classification import RegimeClassifier
from .phase_mapping_components.boundary_analysis import BoundaryAnalyzer
from .phase_mapping_components.resonance_analysis import ResonanceAnalyzer


class PhaseMapper:
    """
    Phase mapping for system behavior classification.

    Physical Meaning:
        Classifies system behavior regimes in parameter space,
        identifying transition boundaries between different
        modes of operation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize phase mapper.

        Args:
            config: Configuration dictionary
        """
        self.config = config

        # Initialize analysis components
        self.regime_classifier = RegimeClassifier(config)
        self.boundary_analyzer = BoundaryAnalyzer()
        self.resonance_analyzer = ResonanceAnalyzer()

    def map_phases(self) -> Dict[str, Any]:
        """
        Map system phases in parameter space.

        Physical Meaning:
            Creates a comprehensive map of system behavior regimes
            in parameter space, identifying transition boundaries
            and regime characteristics.

        Returns:
            Complete phase mapping results
        """
        # Generate parameter grid
        parameter_grid = self._generate_parameter_grid()

        # Classify each point in parameter space
        classifications = self._classify_parameter_space(parameter_grid)

        # Analyze regime boundaries
        boundaries = self.boundary_analyzer.analyze_regime_boundaries(
            parameter_grid, classifications
        )

        # Compute regime statistics
        statistics = self._compute_regime_statistics(classifications)

        # Create phase diagram
        phase_diagram = self._create_phase_diagram(parameter_grid, classifications)

        return {
            "parameter_grid": parameter_grid,
            "classifications": classifications,
            "boundaries": boundaries,
            "statistics": statistics,
            "phase_diagram": phase_diagram,
        }

    def _generate_parameter_grid(self) -> Dict[str, np.ndarray]:
        """Generate parameter grid for phase mapping."""
        # Extract parameter ranges from config
        eta_range = self.config.get("eta_range", [0.0, 0.3])
        chi_double_prime_range = self.config.get("chi_double_prime_range", [0.0, 0.8])
        beta_range = self.config.get("beta_range", [0.6, 1.4])

        # Create parameter grids
        eta_values = np.linspace(eta_range[0], eta_range[1], 20)
        chi_double_prime_values = np.linspace(
            chi_double_prime_range[0], chi_double_prime_range[1], 20
        )
        beta_values = np.linspace(beta_range[0], beta_range[1], 20)

        return {
            "eta": eta_values,
            "chi_double_prime": chi_double_prime_values,
            "beta": beta_values,
        }

    def _classify_parameter_space(
        self, parameter_grid: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """Classify each point in parameter space."""
        classifications = {}

        eta_values = parameter_grid["eta"]
        chi_double_prime_values = parameter_grid["chi_double_prime"]
        beta_values = parameter_grid["beta"]

        for i, eta in enumerate(eta_values):
            for j, chi_double_prime in enumerate(chi_double_prime_values):
                for k, beta in enumerate(beta_values):
                    # Create parameter combination
                    params = {
                        "eta": eta,
                        "chi_double_prime": chi_double_prime,
                        "beta": beta,
                    }

                    # Classify this parameter combination
                    classification = self.regime_classifier.classify_single_point(
                        params
                    )

                    classifications[f"({i},{j},{k})"] = {
                        "parameters": params,
                        "classification": classification,
                    }

        return classifications

    def _compute_regime_statistics(
        self, classifications: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compute statistics for each regime."""
        regime_counts = {}
        regime_scores = {}

        for point_id, classification in classifications.items():
            regime = classification.get("primary_regime", "unknown")
            scores = classification.get("regime_scores", {})

            if regime not in regime_counts:
                regime_counts[regime] = 0
                regime_scores[regime] = []

            regime_counts[regime] += 1
            if regime in scores:
                regime_scores[regime].append(scores[regime])
            else:
                regime_scores[regime].append(0.0)

        # Compute statistics
        statistics = {}
        for regime in regime_counts:
            scores = regime_scores[regime]
            statistics[regime] = {
                "count": regime_counts[regime],
                "percentage": regime_counts[regime] / len(classifications) * 100,
                "mean_score": np.mean(scores),
                "std_score": np.std(scores),
                "min_score": np.min(scores),
                "max_score": np.max(scores),
            }

        return statistics

    def _create_phase_diagram(
        self, parameter_grid: Dict[str, np.ndarray], classifications: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create phase diagram visualization data."""
        # Extract regime information for plotting
        eta_values = parameter_grid["eta"]
        chi_double_prime_values = parameter_grid["chi_double_prime"]
        beta_values = parameter_grid["beta"]

        # Create 2D slices for visualization
        phase_diagram = {}

        # Eta vs Chi_double_prime slice (at beta = 1.0)
        beta_slice = 1.0
        eta_chi_slice = self._create_2d_slice(
            classifications, "eta", "chi_double_prime", beta_slice
        )
        phase_diagram["eta_chi_slice"] = eta_chi_slice

        # Eta vs Beta slice (at chi_double_prime = 0.4)
        chi_slice = 0.4
        eta_beta_slice = self._create_2d_slice(
            classifications, "eta", "beta", chi_slice
        )
        phase_diagram["eta_beta_slice"] = eta_beta_slice

        # Chi_double_prime vs Beta slice (at eta = 0.15)
        eta_slice = 0.15
        chi_beta_slice = self._create_2d_slice(
            classifications, "chi_double_prime", "beta", eta_slice
        )
        phase_diagram["chi_beta_slice"] = chi_beta_slice

        return phase_diagram

    def _create_2d_slice(
        self,
        classifications: Dict[str, Any],
        param1: str,
        param2: str,
        param3_value: float,
    ) -> Dict[str, Any]:
        """Create 2D slice of phase diagram."""
        slice_data = []

        for point_id, classification in classifications.items():
            params = classification["parameters"]

            # Check if this point is in the slice
            if abs(params[param1] - param3_value) < 0.01:  # Tolerance for slice
                slice_data.append(
                    {
                        param1: params[param1],
                        param2: params[param2],
                        "regime": classification["primary_regime"],
                        "scores": classification["regime_scores"],
                    }
                )

        return slice_data

    def classify_resonances(
        self, resonance_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Classify resonances as emergent vs fundamental.

        Physical Meaning:
            Applies criteria from 7d-00-18.md to distinguish between
            emergent resonances (arising from interactions) and
            fundamental resonances (new particles).
        """
        return self.resonance_analyzer.classify_resonances(resonance_data)

    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save phase mapping results to file.

        Args:
            results: Mapping results dictionary
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
