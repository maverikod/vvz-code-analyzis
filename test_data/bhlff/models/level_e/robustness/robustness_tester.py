"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main robustness testing facade for Level E experiments.

This module provides the main RobustnessTester class that coordinates
comprehensive robustness testing for the 7D phase field theory.

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
    >>> tester = RobustnessTester(base_config)
    >>> results = tester.test_noise_robustness(noise_levels)
"""

import numpy as np
from typing import Dict, Any, List
import json

from .noise_testing import NoiseRobustnessTester
from .parameter_testing import ParameterRobustnessTester
from .geometry_testing import GeometryRobustnessTester


class RobustnessTester:
    """
    Main robustness testing facade for system stability.

    Physical Meaning:
        Investigates how the system responds to external perturbations,
        noise, and parameter uncertainties to establish stability
        boundaries and failure modes.
    """

    def __init__(self, base_config: Dict[str, Any]):
        """
        Initialize robustness tester.

        Args:
            base_config: Base configuration for testing
        """
        self.base_config = base_config
        self._setup_testing_modules()

    def _setup_testing_modules(self) -> None:
        """Setup specialized testing modules."""
        self.noise_tester = NoiseRobustnessTester(base_config)
        self.parameter_tester = ParameterRobustnessTester(base_config)
        self.geometry_tester = GeometryRobustnessTester(base_config)

    def test_noise_robustness(self, noise_levels: List[float]) -> Dict[str, Any]:
        """
        Test robustness to BVP-modulation noise.

        Physical Meaning:
            Investigates system response to random perturbations
            in the BVP envelope configuration, simulating environmental
            noise and measurement uncertainties affecting BVP modulations.

        Mathematical Foundation:
            Adds BVP-modulation noise: a(x) → a(x) + ε·N(0,1) where
            ε is the noise amplitude affecting the BVP envelope.

        Args:
            noise_levels: List of noise amplitudes to test

        Returns:
            Analysis of degradation vs noise level
        """
        return self.noise_tester.test_noise_robustness(noise_levels)

    def test_parameter_uncertainty(
        self, uncertainty_ranges: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Test robustness to parameter uncertainties.

        Physical Meaning:
            Investigates how uncertainties in physical parameters
            affect system behavior and stability.

        Args:
            uncertainty_ranges: Dictionary mapping parameters to uncertainty ranges

        Returns:
            Analysis of parameter sensitivity and stability
        """
        return self.parameter_tester.test_parameter_uncertainty(uncertainty_ranges)

    def test_geometry_perturbations(
        self, perturbation_types: List[str]
    ) -> Dict[str, Any]:
        """
        Test robustness to geometry perturbations.

        Physical Meaning:
            Investigates system response to changes in domain
            geometry, boundary conditions, and spatial structure.

        Args:
            perturbation_types: Types of geometry perturbations to test

        Returns:
            Analysis of geometry sensitivity
        """
        return self.geometry_tester.test_geometry_perturbations(perturbation_types)

    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save robustness test results to file.

        Args:
            results: Test results dictionary
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
