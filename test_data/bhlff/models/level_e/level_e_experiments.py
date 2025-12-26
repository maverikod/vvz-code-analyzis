"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main orchestrator for Level E experiments.

This module provides a facade for Level E experiment functionality
in 7D phase field theory, ensuring proper functionality of all
experiment components.

Theoretical Background:
    Level E experiments focus on solitons and topological defects in the
    7D phase field theory, representing fundamental particle-like structures
    with topological protection. These experiments investigate system
    stability, sensitivity, and robustness.

Mathematical Foundation:
    Implements systematic parameter sweeps, sensitivity analysis using
    Sobol indices, and phase space mapping to understand the stability
    boundaries of the theory.

Example:
    >>> experiments = LevelEExperiments(config)
    >>> results = experiments.run_full_analysis()
"""

import numpy as np
from typing import Dict, Any, List, Optional
import json
import logging

from .experiments.experiment_runner import ExperimentRunner
from .experiments.specialized_experiments import SpecializedExperiments


class LevelEExperiments:
    """
    Main orchestrator for Level E experiments.

    Physical Meaning:
        Coordinates comprehensive stability and sensitivity analysis
        of the 7D phase field theory, investigating the robustness
        of solitons and topological defects under various conditions.

    Mathematical Foundation:
        Implements systematic parameter sweeps, sensitivity analysis
        using Sobol indices, and phase space mapping to understand
        the stability boundaries of the theory.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Level E experiments.

        Args:
            config: Configuration dictionary with experiment parameters
        """
        self.config = config
        self._setup_logging()
        self._setup_experiment_components()

    def _setup_logging(self) -> None:
        """Setup logging for experiments."""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _setup_experiment_components(self) -> None:
        """Setup experiment components."""
        # Initialize experiment components
        self.experiment_runner = ExperimentRunner(self.config)
        self.specialized_experiments = SpecializedExperiments()

    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Execute complete Level E analysis suite.

        Physical Meaning:
            Performs comprehensive investigation of system stability
            and sensitivity, providing complete characterization of
            the 7D phase field theory behavior.

        Returns:
            Dict containing all analysis results and metrics
        """
        return self.experiment_runner.run_full_analysis()

    def run_soliton_experiments(self) -> Dict[str, Any]:
        """
        Run specialized soliton experiments.

        Physical Meaning:
            Performs detailed analysis of soliton solutions including
            stability analysis, energy computation, and topological
            charge verification.
        """
        return self.specialized_experiments.run_soliton_experiments()

    def run_defect_experiments(self) -> Dict[str, Any]:
        """
        Run specialized defect experiments.

        Physical Meaning:
            Performs detailed analysis of topological defects including
            dynamics simulation, interaction analysis, and formation processes.
        """
        return self.specialized_experiments.run_defect_experiments()

    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save Level E experiment results to file.

        Args:
            results: Experiment results dictionary
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
