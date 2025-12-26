"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Grid convergence analysis for Level E experiments.

This module implements grid convergence analysis for the 7D phase field theory,
investigating how results change as the computational grid is refined.

Theoretical Background:
    Grid convergence analysis investigates how results change as the computational
    grid is refined, establishing convergence rates and optimal grid sizes.

Mathematical Foundation:
    Computes convergence rate: p = log(|e_h1|/|e_h2|)/log(h1/h2)
    where e_h is the error at grid spacing h.

Example:
    >>> analyzer = GridConvergenceAnalyzer(reference_config)
    >>> results = analyzer.analyze_grid_convergence(grid_sizes)
"""

import numpy as np
from typing import Dict, Any, List


class GridConvergenceAnalyzer:
    """
    Grid convergence analysis for discretization effects.

    Physical Meaning:
        Investigates how results change as the computational
        grid is refined, establishing convergence rates and
        optimal grid sizes.
    """

    def __init__(self, reference_config: Dict[str, Any]):
        """
        Initialize grid convergence analyzer.

        Args:
            reference_config: Reference configuration for comparison
        """
        self.reference_config = reference_config
        self._setup_convergence_metrics()

    def _setup_convergence_metrics(self) -> None:
        """Setup metrics for convergence analysis."""
        self.convergence_metrics = [
            "power_law_exponent",
            "topological_charge",
            "energy",
            "quality_factor",
            "stability",
        ]

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
        results = {}

        for grid_size in grid_sizes:
            print(f"Analyzing grid size: {grid_size}")

            # Create configuration with specified grid size
            config = self._create_grid_config(grid_size)

            # Run simulation
            output = self._run_simulation(config)

            # Compute metrics
            metrics = self._compute_metrics(output)

            results[grid_size] = {
                "config": config,
                "output": output,
                "metrics": metrics,
            }

        # Analyze convergence
        convergence_analysis = self._analyze_convergence(results)

        # Recommend optimal grid size
        recommended_size = self._recommend_grid_size(convergence_analysis)

        return {
            "grid_results": results,
            "convergence_analysis": convergence_analysis,
            "recommended_grid_size": recommended_size,
        }

    def _create_grid_config(self, grid_size: int) -> Dict[str, Any]:
        """Create configuration with specified grid size."""
        config = self.reference_config.copy()
        config["N"] = grid_size

        # Adjust domain size if needed to maintain resolution
        if "L" in config:
            # Keep physical resolution approximately constant
            base_N = config.get("base_N", 256)
            if base_N != grid_size:
                scale_factor = base_N / grid_size
                config["L"] *= scale_factor

        return config

    def _run_simulation(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run simulation with given configuration.

        Physical Meaning:
            Executes the 7D phase field simulation with specified
            discretization parameters and returns key observables.
        """
        # Placeholder implementation - in real case, this would run
        # the actual 7D phase field simulation

        # Extract key parameters
        N = config.get("N", 256)
        L = config.get("L", 20.0)
        beta = config.get("beta", 1.0)
        mu = config.get("mu", 1.0)

        # Compute observables with grid-dependent effects
        dx = L / N  # Grid spacing

        # Power law exponent (should be grid-independent)
        power_law_exponent = 2 * beta - 3

        # Topological charge (may have discretization errors)
        topological_charge = 1.0 + np.random.normal(0, 0.01 * dx)

        # Energy (scales with grid resolution)
        energy = mu * beta * (1 + 0.1 * dx)

        # Quality factor (may depend on resolution)
        quality_factor = mu / (0.1 + 0.01 * dx)

        # Stability (should be grid-independent)
        stability = 1.0 if beta > 0.5 else 0.0

        return {
            "power_law_exponent": power_law_exponent,
            "topological_charge": topological_charge,
            "energy": energy,
            "quality_factor": quality_factor,
            "stability": stability,
            "grid_spacing": dx,
            "grid_size": N,
        }

    def _compute_metrics(self, output: Dict[str, Any]) -> Dict[str, float]:
        """Compute convergence metrics from simulation output."""
        metrics = {}

        for metric in self.convergence_metrics:
            if metric in output:
                metrics[metric] = output[metric]

        return metrics

    def _analyze_convergence(
        self, results: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze convergence behavior.

        Physical Meaning:
            Computes convergence rates and identifies optimal
            grid sizes for different observables.
        """
        grid_sizes = sorted(results.keys())
        convergence_rates = {}
        convergence_quality = {}

        for metric in self.convergence_metrics:
            if metric in results[grid_sizes[0]]["metrics"]:
                # Extract values for this metric
                values = [
                    results[grid_size]["metrics"][metric] for grid_size in grid_sizes
                ]

                # Compute convergence rate
                convergence_rate = self._compute_convergence_rate(grid_sizes, values)
                convergence_rates[metric] = convergence_rate

                # Assess convergence quality
                quality = self._assess_convergence_quality(values)
                convergence_quality[metric] = quality

        # Overall convergence analysis
        overall_convergence = self._analyze_overall_convergence(convergence_rates)

        return {
            "convergence_rates": convergence_rates,
            "convergence_quality": convergence_quality,
            "overall_convergence": overall_convergence,
            "grid_sizes": grid_sizes,
        }

    def _compute_convergence_rate(
        self, grid_sizes: List[int], values: List[float]
    ) -> float:
        """
        Compute convergence rate for a metric.

        Mathematical Foundation:
            p = log(|e_h1|/|e_h2|)/log(h1/h2) where e_h is the error
            at grid spacing h.
        """
        if len(values) < 2:
            return 0.0

        # Use finest grid as reference
        reference_value = values[-1]
        errors = [abs(v - reference_value) for v in values]

        # Compute convergence rate
        convergence_rates = []
        for i in range(len(errors) - 1):
            if errors[i] > 0 and errors[i + 1] > 0:
                h1 = 1.0 / grid_sizes[i]
                h2 = 1.0 / grid_sizes[i + 1]
                rate = np.log(errors[i] / errors[i + 1]) / np.log(h1 / h2)
                convergence_rates.append(rate)

        return np.mean(convergence_rates) if convergence_rates else 0.0

    def _assess_convergence_quality(self, values: List[float]) -> Dict[str, Any]:
        """Assess quality of convergence."""
        if len(values) < 2:
            return {"quality": "insufficient_data", "score": 0.0}

        # Compute relative changes
        relative_changes = []
        for i in range(len(values) - 1):
            if values[i + 1] != 0:
                rel_change = abs(values[i] - values[i + 1]) / abs(values[i + 1])
                relative_changes.append(rel_change)

        # Assess convergence quality
        max_change = max(relative_changes) if relative_changes else 0.0
        mean_change = np.mean(relative_changes) if relative_changes else 0.0

        if max_change < 0.01:
            quality = "excellent"
            score = 1.0
        elif max_change < 0.05:
            quality = "good"
            score = 0.8
        elif max_change < 0.1:
            quality = "fair"
            score = 0.6
        else:
            quality = "poor"
            score = 0.3

        return {
            "quality": quality,
            "score": score,
            "max_change": max_change,
            "mean_change": mean_change,
        }

    def _analyze_overall_convergence(
        self, convergence_rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Analyze overall convergence behavior."""
        rates = list(convergence_rates.values())

        if not rates:
            return {"overall_rate": 0.0, "quality": "unknown"}

        # Compute overall convergence rate
        overall_rate = np.mean(rates)

        # Assess overall quality
        if overall_rate > 2.0:
            quality = "excellent"
        elif overall_rate > 1.0:
            quality = "good"
        elif overall_rate > 0.5:
            quality = "fair"
        else:
            quality = "poor"

        return {
            "overall_rate": overall_rate,
            "quality": quality,
            "individual_rates": convergence_rates,
        }

    def _recommend_grid_size(self, convergence_analysis: Dict[str, Any]) -> int:
        """Recommend optimal grid size based on convergence analysis."""
        grid_sizes = convergence_analysis["grid_sizes"]
        convergence_rates = convergence_analysis["convergence_rates"]

        # Find grid size where convergence is good but not excessive
        for grid_size in grid_sizes:
            # Check if convergence is good at this grid size
            good_convergence = True
            for metric, rate in convergence_rates.items():
                if rate < 1.0:  # Poor convergence
                    good_convergence = False
                    break

            if good_convergence:
                return grid_size

        # Default to largest grid size if no good convergence found
        return max(grid_sizes)
