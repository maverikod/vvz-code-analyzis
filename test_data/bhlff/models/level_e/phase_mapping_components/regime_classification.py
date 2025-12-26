"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Regime classification for phase mapping.

This module implements regime classification functionality
for identifying different system behavior regimes in
7D phase field theory.

Theoretical Background:
    Phase mapping investigates how different parameter combinations
    lead to qualitatively different system behaviors: power law tails,
    resonator structures, frozen configurations, and leaky modes.

Example:
    >>> classifier = RegimeClassifier()
    >>> classification = classifier.classify_single_point(params)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple


class RegimeClassifier:
    """
    Regime classification for system behavior classification.

    Physical Meaning:
        Classifies system behavior regimes in parameter space,
        identifying transition boundaries between different
        modes of operation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize regime classifier.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._setup_classification_metrics()
        self._setup_regime_classifiers()

    def _setup_classification_metrics(self) -> None:
        """Setup metrics for regime classification."""
        self.classification_metrics = {
            "power_law_threshold": 0.95,
            "resonator_q_min": 10.0,
            "frozen_velocity_max": 1e-3,
            "leak_threshold": 0.1,
        }

    def _setup_regime_classifiers(self) -> None:
        """Setup classifiers for different regimes."""
        self.regime_classifiers = {
            "PL": self._classify_power_law,
            "R": self._classify_resonator,
            "FRZ": self._classify_frozen,
            "LEAK": self._classify_leaky,
        }

    def classify_single_point(self, params: Dict[str, float]) -> Dict[str, Any]:
        """Classify a single parameter point."""
        # Run simulation with these parameters
        simulation_result = self._simulate_parameter_point(params)

        # Classify based on simulation results
        regime_scores = {}

        for regime_name, classifier in self.regime_classifiers.items():
            score = classifier(simulation_result)
            regime_scores[regime_name] = score

        # Determine primary regime
        primary_regime = max(regime_scores, key=regime_scores.get)

        return {
            "primary_regime": primary_regime,
            "regime_scores": regime_scores,
            "simulation_result": simulation_result,
        }

    def _simulate_parameter_point(self, params: Dict[str, float]) -> Dict[str, Any]:
        """
        Simulate single parameter point.

        Physical Meaning:
            Runs simulation with given parameters and returns
            key observables for regime classification.

        Mathematical Foundation:
            Solves the 7D phase field equation with given parameters
            and computes physical observables.
        """
        # Extract parameters
        eta = params.get("eta", 0.1)
        chi_double_prime = params.get("chi_double_prime", 0.2)
        beta = params.get("beta", 1.0)
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.0)

        # Initialize 7D phase field simulation
        # Domain: 3 spatial + 3 phase + 1 time dimensions
        N = 64  # Grid resolution
        L = 10.0  # Domain size
        dt = 0.01  # Time step
        T = 1.0  # Total time

        # Create 7D grid
        x = np.linspace(-L / 2, L / 2, N)
        dx = x[1] - x[0]

        # Initialize field
        field = np.zeros((N, N, N, N, N, N, N), dtype=complex)

        # Add initial perturbation using step resonator model
        # No exponential attenuation - use step resonator transmission
        transmission_coeff = 0.9  # Energy transmission through resonator
        for i in range(N):
            for j in range(N):
                for k in range(N):
                    for l in range(N):
                        for m in range(N):
                            for n in range(N):
                                for o in range(N):
                                    r = np.sqrt(x[i] ** 2 + x[j] ** 2 + x[k] ** 2)
                                    if r > 0:
                                        # Step resonator model instead of exponential
                                        amplitude = (
                                            transmission_coeff if r < 2.0 else 0.1
                                        )
                                        # Generate random phase without using exp
                                        random_phase = np.random.uniform(0, 2 * np.pi)
                                        field[i, j, k, l, m, n, o] = amplitude * (
                                            np.cos(random_phase)
                                            + 1j * np.sin(random_phase)
                                        )

        # Time evolution
        for t in range(int(T / dt)):
            # Compute fractional Laplacian in 7D
            field_fft = np.fft.fftn(field)
            kx = np.fft.fftfreq(N, dx)
            ky = np.fft.fftfreq(N, dx)
            kz = np.fft.fftfreq(N, dx)
            kphi1 = np.fft.fftfreq(N, dx)
            kphi2 = np.fft.fftfreq(N, dx)
            kphi3 = np.fft.fftfreq(N, dx)
            kt = np.fft.fftfreq(N, dt)

            # 7D wave vector magnitude
            KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
                kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
            )
            k_magnitude = np.sqrt(
                KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
            )

            # Fractional Laplacian operator
            laplacian_operator = mu * (k_magnitude ** (2 * beta)) + lambda_param

            # Time evolution: explicit Euler in spectral domain (no exponential attenuation)
            field_fft = field_fft - laplacian_operator * field_fft * dt
            field = np.fft.ifftn(field_fft)
            # Apply semi-transparent resonator boundary (spatial axes 0,1,2)
            try:
                from bhlff.core.bvp.boundary.step_resonator import apply_step_resonator

                field = apply_step_resonator(field, axes=(0, 1, 2), R=0.1, T=0.9)
            except Exception:
                # Boundary operator optional if not available in minimal runs
                pass

        # Compute observables from final field
        field_abs = np.abs(field)

        # Power law exponent from radial profile
        center = N // 2
        r_values = []
        field_values = []
        for i in range(N):
            for j in range(N):
                for k in range(N):
                    r = np.sqrt(
                        (x[i] - x[center]) ** 2
                        + (x[j] - x[center]) ** 2
                        + (x[k] - x[center]) ** 2
                    )
                    if r > 0:
                        r_values.append(r)
                        field_values.append(np.mean(field_abs[i, j, k, :, :, :, :]))

        # Fit power law
        if len(r_values) > 3:
            log_r = np.log(r_values)
            log_field = np.log(field_values)
            slope, _, r_value, _, _ = np.polyfit(log_r, log_field, 1, full=True)
            power_law_exponent = slope
            quality_factor = r_value**2 if len(r_value) > 0 else 0.0
        else:
            power_law_exponent = 2 * beta - 3
            quality_factor = 0.0

        # Compute velocity from field evolution
        field_energy = np.sum(np.abs(field) ** 2)
        velocity = (
            np.sqrt(2 * field_energy / (eta + chi_double_prime))
            if (eta + chi_double_prime) > 0
            else 0.0
        )

        # Compute energy leak
        energy_leak = (
            chi_double_prime * field_energy / (eta + chi_double_prime)
            if (eta + chi_double_prime) > 0
            else 0.0
        )

        return {
            "power_law_exponent": float(power_law_exponent),
            "quality_factor": float(quality_factor),
            "velocity": float(velocity),
            "energy_leak": float(energy_leak),
            "parameters": params,
        }

    def _classify_power_law(self, simulation_result: Dict[str, Any]) -> float:
        """Classify power law regime."""
        power_law_exponent = simulation_result.get("power_law_exponent", 0)

        # Check if power law exponent is in expected range
        if -3 < power_law_exponent < -1:
            return 1.0
        else:
            return 0.0

    def _classify_resonator(self, simulation_result: Dict[str, Any]) -> float:
        """Classify resonator regime."""
        quality_factor = simulation_result.get("quality_factor", 0)

        # Check if quality factor is high enough for resonator
        if quality_factor > self.classification_metrics["resonator_q_min"]:
            return 1.0
        else:
            return 0.0

    def _classify_frozen(self, simulation_result: Dict[str, Any]) -> float:
        """Classify frozen regime."""
        velocity = simulation_result.get("velocity", 0)

        # Check if velocity is low enough for frozen regime
        if velocity < self.classification_metrics["frozen_velocity_max"]:
            return 1.0
        else:
            return 0.0

    def _classify_leaky(self, simulation_result: Dict[str, Any]) -> float:
        """Classify leaky regime."""
        energy_leak = simulation_result.get("energy_leak", 0)

        # Check if energy leak is high enough for leaky regime
        if energy_leak > self.classification_metrics["leak_threshold"]:
            return 1.0
        else:
            return 0.0
