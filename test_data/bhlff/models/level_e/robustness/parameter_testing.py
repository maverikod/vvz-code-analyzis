"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Parameter robustness testing for Level E experiments.

This module implements parameter robustness testing for the 7D phase field theory,
investigating system stability under parameter uncertainties and variations.

Theoretical Background:
    Parameter robustness testing investigates how uncertainties in physical
    parameters affect system behavior and stability, establishing parameter
    sensitivity boundaries and failure modes.

Mathematical Foundation:
    Tests system response to parameter perturbations: p → p + δp where
    δp represents parameter uncertainties or systematic variations.

Example:
    >>> tester = ParameterRobustnessTester(base_config)
    >>> results = tester.test_parameter_uncertainty(uncertainty_ranges)
"""

import numpy as np
from typing import Dict, Any, List


class ParameterRobustnessTester:
    """
    Parameter robustness testing for system stability.

    Physical Meaning:
        Investigates how uncertainties in physical parameters
        affect system behavior and stability.
    """

    def __init__(self, base_config: Dict[str, Any]):
        """
        Initialize parameter robustness tester.

        Args:
            base_config: Base configuration for testing
        """
        self.base_config = base_config
        self._setup_parameter_perturbation_generators()

    def _setup_parameter_perturbation_generators(self) -> None:
        """Setup generators for different types of parameter perturbations."""
        self._param_perturbation_generators = {
            "uniform": self._generate_uniform_param_perturbation,
            "gaussian": self._generate_gaussian_param_perturbation,
            "systematic": self._generate_systematic_param_perturbation,
        }

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
        results = {}

        for param_name, uncertainty in uncertainty_ranges.items():
            print(f"Testing parameter uncertainty: {param_name} ± {uncertainty}")

            # Generate parameter variations
            param_variations = self._generate_parameter_variations(
                param_name, uncertainty
            )

            # Run simulations with varied parameters
            outputs = self._run_simulations_with_param_variations(
                param_name, param_variations
            )

            # Analyze sensitivity to parameter uncertainty
            sensitivity = self._analyze_parameter_sensitivity(outputs, param_variations)

            results[param_name] = {
                "uncertainty": uncertainty,
                "variations": param_variations,
                "outputs": outputs,
                "sensitivity": sensitivity,
            }

        return results

    def _generate_parameter_variations(
        self, param_name: str, uncertainty: float
    ) -> np.ndarray:
        """Generate parameter variations for uncertainty testing."""
        base_value = self.base_config.get(param_name, 1.0)

        # Generate variations within uncertainty range
        variations = np.random.normal(base_value, uncertainty * base_value, 20)

        return variations

    def _run_simulations_with_param_variations(
        self, param_name: str, variations: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Run simulations with parameter variations."""
        outputs = []

        for variation in variations:
            config = self.base_config.copy()
            config[param_name] = variation

            try:
                output = self._simulate_single_case(config)
                outputs.append(output)
            except Exception as e:
                print(f"Simulation failed for {param_name}={variation}: {e}")
                outputs.append(None)

        return outputs

    def _simulate_single_case(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate single configuration case.

        Physical Meaning:
            Runs a single simulation with given configuration and returns
            key observables for robustness analysis.
        """
        # Placeholder implementation - in real case, this would run
        # the actual 7D phase field simulation

        # Extract key parameters
        beta = config.get("beta", 1.0)
        mu = config.get("mu", 1.0)
        eta = config.get("eta", 0.1)

        # Compute observables
        power_law_exponent = 2 * beta - 3
        quality_factor = mu / eta if eta > 0 else float("inf")

        # Add some realistic variations
        noise = np.random.normal(0, 0.05)

        return {
            "power_law_exponent": power_law_exponent + noise,
            "quality_factor": quality_factor,
            "energy": mu * beta,
            "stability": 1.0 if beta > 0.5 else 0.0,
        }

    def _analyze_parameter_sensitivity(
        self, outputs: List[Dict[str, Any]], variations: np.ndarray
    ) -> Dict[str, Any]:
        """Analyze sensitivity to parameter variations."""
        if not outputs or all(o is None for o in outputs):
            return {"sensitivity": 0.0, "correlation": 0.0}

        # Extract valid outputs and variations
        valid_outputs = []
        valid_variations = []

        for i, (output, variation) in enumerate(zip(outputs, variations)):
            if output is not None:
                valid_outputs.append(output)
                valid_variations.append(variation)

        if len(valid_outputs) < 2:
            return {"sensitivity": 0.0, "correlation": 0.0}

        # Compute sensitivity metrics
        sensitivity_metrics = {}

        for metric in ["power_law_exponent", "quality_factor", "energy"]:
            if metric in valid_outputs[0]:
                values = [o[metric] for o in valid_outputs if metric in o]
                if len(values) > 1:
                    try:
                        correlation = np.corrcoef(
                            valid_variations[: len(values)], values
                        )[0, 1]
                        if np.isnan(correlation):
                            correlation = 0.0
                        sensitivity_metrics[metric] = abs(correlation)
                    except:
                        sensitivity_metrics[metric] = 0.0

        # Overall sensitivity
        overall_sensitivity = np.mean(list(sensitivity_metrics.values()))

        # Compute correlation safely
        try:
            if len(valid_outputs) > 1 and len(valid_variations) > 1:
                correlation = np.corrcoef(
                    valid_variations,
                    [o.get("power_law_exponent", 0) for o in valid_outputs],
                )[0, 1]
                if np.isnan(correlation):
                    correlation = 0.0
            else:
                correlation = 0.0
        except:
            correlation = 0.0

        return {
            "sensitivity": overall_sensitivity,
            "metrics": sensitivity_metrics,
            "correlation": correlation,
        }

    def _generate_uniform_param_perturbation(
        self, param_name: str, uncertainty: float
    ) -> float:
        """Generate uniform parameter perturbation."""
        base_value = self.base_config.get(param_name, 1.0)
        return base_value + np.random.uniform(-uncertainty, uncertainty)

    def _generate_gaussian_param_perturbation(
        self, param_name: str, uncertainty: float
    ) -> float:
        """Generate Gaussian parameter perturbation."""
        base_value = self.base_config.get(param_name, 1.0)
        return base_value + np.random.normal(0, uncertainty)

    def _generate_systematic_param_perturbation(
        self, param_name: str, uncertainty: float
    ) -> float:
        """Generate systematic parameter perturbation."""
        base_value = self.base_config.get(param_name, 1.0)
        # Systematic perturbation (e.g., temperature drift)
        return base_value * (1 + uncertainty)
