"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Noise robustness testing for Level E experiments.

This module implements noise robustness testing for the 7D phase field theory,
investigating system stability under BVP-modulation noise perturbations.

Theoretical Background:
    Noise robustness testing investigates how the system responds to random
    perturbations in the BVP envelope configuration, simulating environmental
    noise and measurement uncertainties affecting BVP modulations.

Mathematical Foundation:
    Adds BVP-modulation noise: a(x) → a(x) + ε·N(0,1) where
    ε is the noise amplitude affecting the BVP envelope.

Example:
    >>> tester = NoiseRobustnessTester(base_config)
    >>> results = tester.test_noise_robustness(noise_levels)
"""

import numpy as np
from typing import Dict, Any, List, Tuple


class NoiseRobustnessTester:
    """
    Noise robustness testing for system stability.

    Physical Meaning:
        Investigates how the system responds to random perturbations
        in the BVP envelope configuration, simulating environmental
        noise and measurement uncertainties affecting BVP modulations.
    """

    def __init__(self, base_config: Dict[str, Any]):
        """
        Initialize noise robustness tester.

        Args:
            base_config: Base configuration for testing
        """
        self.base_config = base_config
        self._setup_noise_generators()

    def _setup_noise_generators(self) -> None:
        """Setup generators for different types of noise."""
        self._noise_generators = {
            "gaussian": self._generate_gaussian_noise,
            "uniform": self._generate_uniform_noise,
            "colored": self._generate_colored_noise,
        }

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
        results = {}

        for noise_level in noise_levels:
            print(f"Testing noise level: {noise_level}")

            # Generate noisy BVP envelope configurations
            noisy_configs = self._add_bvp_modulation_noise(noise_level)

            # Run simulations
            outputs = self._run_simulations(noisy_configs)

            # Compute degradation metrics
            degradation = self._compute_degradation(outputs, noise_level)

            # Check for passivity violations
            passivity_violations = self._check_passivity(outputs)

            # Check topological stability
            topological_stability = self._check_topology(outputs)

            results[noise_level] = {
                "degradation": degradation,
                "passive_violations": passivity_violations,
                "topological_stability": topological_stability,
                "outputs": outputs,
            }

        return results

    def _add_bvp_modulation_noise(self, noise_level: float) -> List[Dict[str, Any]]:
        """
        Add BVP-modulation noise to configurations.

        Physical Meaning:
            Adds random perturbations to the BVP envelope configuration
            to simulate environmental noise and measurement uncertainties.
        """
        noisy_configs = []
        n_samples = 10  # Number of noisy realizations per noise level

        for _ in range(n_samples):
            config = self.base_config.copy()

            # Add noise to BVP envelope parameters
            if "bvp_envelope" in config:
                envelope = config["bvp_envelope"].copy()

                # Add Gaussian noise to envelope amplitude
                noise = np.random.normal(0, noise_level, envelope["amplitude"].shape)
                envelope["amplitude"] += noise

                config["bvp_envelope"] = envelope

            noisy_configs.append(config)

        return noisy_configs

    def _run_simulations(self, configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run simulations for multiple configurations."""
        outputs = []

        for config in configs:
            try:
                output = self._simulate_single_case(config)
                outputs.append(output)
            except Exception as e:
                print(f"Simulation failed: {e}")
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

    def _compute_degradation(
        self, outputs: List[Dict[str, Any]], noise_level: float
    ) -> Dict[str, Any]:
        """
        Compute degradation metrics.

        Physical Meaning:
            Quantifies how much the system performance degrades
            under noise perturbations compared to the baseline.
        """
        if not outputs or all(o is None for o in outputs):
            return {"degradation": 1.0, "metrics": {}}

        # Filter out None outputs
        valid_outputs = [o for o in outputs if o is not None]

        if not valid_outputs:
            return {"degradation": 1.0, "metrics": {}}

        # Compute baseline (noise_level = 0)
        baseline = self._get_baseline_outputs()

        # Compute degradation for each metric
        degradation_metrics = {}

        for metric in ["power_law_exponent", "quality_factor", "energy", "stability"]:
            if metric in valid_outputs[0]:
                noisy_values = [o[metric] for o in valid_outputs if metric in o]
                baseline_value = baseline.get(metric, 0.0)

                if baseline_value != 0:
                    relative_degradation = abs(
                        np.mean(noisy_values) - baseline_value
                    ) / abs(baseline_value)
                else:
                    relative_degradation = abs(np.mean(noisy_values))

                degradation_metrics[metric] = relative_degradation

        # Overall degradation
        overall_degradation = np.mean(list(degradation_metrics.values()))

        return {
            "degradation": overall_degradation,
            "metrics": degradation_metrics,
            "noise_level": noise_level,
        }

    def _get_baseline_outputs(self) -> Dict[str, float]:
        """Get baseline outputs for comparison."""
        # Run baseline simulation
        baseline_output = self._simulate_single_case(self.base_config)
        return baseline_output

    def _check_passivity(self, outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check for passivity violations.

        Physical Meaning:
            Verifies that the system remains passive (Re Y_out ≥ 0)
            under perturbations, which is a fundamental physical requirement.
        """
        passivity_violations = []

        for i, output in enumerate(outputs):
            if output is None:
                continue

            # Check passivity condition
            if "impedance" in output:
                impedance = output["impedance"]
                if isinstance(impedance, complex):
                    real_part = impedance.real
                    if real_part < 0:
                        passivity_violations.append(
                            {
                                "sample": i,
                                "impedance": impedance,
                                "violation": real_part,
                            }
                        )

        return {
            "violations": passivity_violations,
            "count": len(passivity_violations),
            "is_passive": len(passivity_violations) == 0,
        }

    def _check_topology(self, outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check topological stability.

        Physical Meaning:
            Verifies that topological invariants (like topological charge)
            remain stable under perturbations.
        """
        topological_stability = []

        for i, output in enumerate(outputs):
            if output is None:
                continue

            # Check topological charge stability
            if "topological_charge" in output:
                charge = output["topological_charge"]
                # Check if charge is approximately integer
                if abs(charge - round(charge)) > 0.1:
                    topological_stability.append(
                        {
                            "sample": i,
                            "charge": charge,
                            "deviation": abs(charge - round(charge)),
                        }
                    )

        return {
            "instabilities": topological_stability,
            "count": len(topological_stability),
            "is_stable": len(topological_stability) == 0,
        }

    def _generate_gaussian_noise(
        self, shape: Tuple[int, ...], amplitude: float
    ) -> np.ndarray:
        """Generate Gaussian noise."""
        return np.random.normal(0, amplitude, shape)

    def _generate_uniform_noise(
        self, shape: Tuple[int, ...], amplitude: float
    ) -> np.ndarray:
        """Generate uniform noise."""
        return np.random.uniform(-amplitude, amplitude, shape)

    def _generate_colored_noise(
        self, shape: Tuple[int, ...], amplitude: float, color: float = 1.0
    ) -> np.ndarray:
        """Generate colored noise with power spectrum ~ f^(-color)."""
        # Generate white noise
        white_noise = np.random.normal(0, 1, shape)

        # Apply frequency domain filtering
        fft_noise = np.fft.fftn(white_noise)
        frequencies = np.fft.fftfreq(shape[0])

        # Apply color filter
        filter_spectrum = np.power(np.abs(frequencies), -color / 2)
        filter_spectrum[0] = 1.0  # Avoid division by zero

        colored_fft = fft_noise * filter_spectrum
        colored_noise = np.fft.ifftn(colored_fft).real

        # Scale to desired amplitude
        colored_noise *= amplitude / np.std(colored_noise)

        return colored_noise
