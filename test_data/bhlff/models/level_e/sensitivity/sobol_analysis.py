"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Sobol sensitivity analysis for parameter ranking.

This module implements Sobol sensitivity analysis functionality
for ranking parameter importance in 7D phase field theory.

Theoretical Background:
    Sobol sensitivity analysis quantifies the relative importance
    of different parameters in determining system behavior using
    variance decomposition methods.

Example:
    >>> analyzer = SobolAnalyzer(parameter_ranges)
    >>> indices = analyzer.compute_sobol_indices(samples, outputs)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from scipy import stats


class SobolAnalyzer:
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
        # Generate Latin Hypercube samples
        samples = np.zeros((n_samples, self.n_params))

        for i, (param_name, (min_val, max_val)) in enumerate(self.param_ranges.items()):
            # Generate uniform samples in [0, 1]
            uniform_samples = np.random.uniform(0, 1, n_samples)

            # Apply Latin Hypercube sampling
            lhs_samples = (uniform_samples + np.arange(n_samples)) / n_samples

            # Scale to parameter range
            samples[:, i] = min_val + lhs_samples * (max_val - min_val)

        return samples

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
        # Compute total variance
        total_variance = np.var(outputs)

        if total_variance == 0:
            return {name: 0.0 for name in self.param_names}

        sobol_indices = {}

        for i, param_name in enumerate(self.param_names):
            # First-order Sobol index
            first_order = self._compute_first_order_index(samples, outputs, i)

            # Total-order Sobol index
            total_order = self._compute_total_order_index(samples, outputs, i)

            sobol_indices[param_name] = {
                "first_order": first_order,
                "total_order": total_order,
                "interaction": total_order - first_order,
            }

        return sobol_indices

    def _compute_first_order_index(
        self, samples: np.ndarray, outputs: np.ndarray, param_idx: int
    ) -> float:
        """Compute first-order Sobol index for parameter."""
        # Group outputs by parameter value (binning)
        param_values = samples[:, param_idx]
        n_bins = min(20, len(np.unique(param_values)))

        # Create bins
        bins = np.linspace(np.min(param_values), np.max(param_values), n_bins + 1)
        bin_indices = np.digitize(param_values, bins) - 1

        # Compute conditional expectations
        conditional_means = []
        for bin_idx in range(n_bins):
            mask = bin_indices == bin_idx
            if np.sum(mask) > 0:
                conditional_means.append(np.mean(outputs[mask]))
            else:
                conditional_means.append(0.0)

        # Compute variance of conditional expectations
        conditional_variance = np.var(conditional_means)
        total_variance = np.var(outputs)

        if total_variance == 0:
            return 0.0

        return conditional_variance / total_variance

    def _compute_total_order_index(
        self, samples: np.ndarray, outputs: np.ndarray, param_idx: int
    ) -> float:
        """
        Compute total-order Sobol index for parameter using Monte Carlo estimation.

        Physical Meaning:
            Calculates the total contribution of a parameter to output variance,
            including all interactions with other parameters, using Saltelli's
            Monte Carlo method for robust estimation.

        Mathematical Foundation:
            S_Ti = 1 - Var[E[Y|X_{~i}]]/Var[Y]
            where X_{~i} are all parameters except i
        """
        n_samples = len(samples)
        param_values = samples[:, param_idx]

        # Split samples into two independent sets for Monte Carlo estimation
        n_half = n_samples // 2
        samples_A = samples[:n_half]
        samples_B = samples[n_half : 2 * n_half]
        outputs_A = outputs[:n_half]
        outputs_B = outputs[n_half : 2 * n_half]

        # Create resampled set: all parameters from A except param_idx from B
        samples_AB = samples_A.copy()
        samples_AB[:, param_idx] = samples_B[:, param_idx]

        # Compute outputs for resampled set
        outputs_AB = self._run_simulations(samples_AB)

        # Calculate total-order index using Saltelli's formula
        # E_Ti = 0.5 * E[(f(A) - f(AB))^2]
        numerator = 0.5 * np.mean((outputs_A - outputs_AB) ** 2)
        denominator = np.var(outputs)

        if denominator == 0:
            return 0.0

        total_order = numerator / denominator

        # Ensure index is in valid range [0, 1]
        total_order = np.clip(total_order, 0.0, 1.0)

        return total_order

    def _run_simulations(self, samples: np.ndarray) -> np.ndarray:
        """
        Run simulations for parameter samples.

        Physical Meaning:
            Executes the 7D phase field simulations for each parameter
            combination to generate output data for sensitivity analysis.
        """
        outputs = []

        for i, sample in enumerate(samples):
            try:
                # Create parameter dictionary
                params = dict(zip(self.param_names, sample))

                # Run full 7D simulation
                output = self._simulate_single_case(params)
                outputs.append(output)

            except Exception as e:
                # Handle simulation failures
                print(f"Simulation failed for sample {i}: {e}")
                outputs.append(np.nan)

        return np.array(outputs)

    def _simulate_single_case(self, params: Dict[str, float]) -> float:
        """
        Simulate single parameter case using full 7D BVP phase field simulation.

        Physical Meaning:
            Runs a complete 7D phase field simulation with given parameters
            and returns a key observable (power law exponent for tail behavior).

        Mathematical Foundation:
            Solves the 7D phase field equation with fractional Laplacian:
            L_β a = μ(-Δ)^β a = s(x,t)
            and analyzes the resulting field configuration.
        """
        from ...core.domain.domain_7d import Domain7D
        from ...solvers.spectral.fft_solver_7d import FFTSolver7D
        from ...models.level_b.power_law_tails import PowerLawAnalyzer

        # Extract key parameters
        beta = params.get("beta", 1.0)
        mu = params.get("mu", 1.0)
        eta = params.get("eta", 0.1)
        lambda_param = params.get("lambda", 0.0)

        # Create compact 7D domain for efficiency
        domain_size = 32  # Reduced for sensitivity analysis
        domain = Domain7D(
            L_spatial=10.0,
            N_spatial=domain_size,
            L_phase=2 * np.pi,
            N_phase=domain_size,
            L_temporal=1.0,
            N_temporal=domain_size,
        )

        # Setup solver with parameters
        solver_params = {
            "beta": beta,
            "mu": mu,
            "lambda": lambda_param,
            "eta": eta,
            "precision": "float64",
        }

        try:
            solver = FFTSolver7D(domain, solver_params)

            # Create localized source term
            source = self._create_source_field(domain, eta)

            # Solve for phase field
            solution = solver.solve(source)

            # Analyze power law tail
            analyzer = PowerLawAnalyzer(domain, solver_params)
            power_law_results = analyzer.analyze_power_law_tail(solution)

            # Extract observable: power law exponent
            observable = power_law_results.get("exponent", 2 * beta - 3)

            # Add complexity metric: topological charge
            if "topological_charge" in power_law_results:
                complexity = abs(power_law_results["topological_charge"])
                observable += 0.1 * complexity

            return observable

        except Exception as e:
            # Fallback to analytical estimate if simulation fails
            print(f"Simulation failed: {e}. Using analytical estimate.")
            return 2 * beta - 3

    def _create_source_field(self, domain: "Domain7D", eta: float) -> np.ndarray:
        """
        Create localized source field for 7D simulation.

        Physical Meaning:
            Generates a localized excitation in the 7D phase space-time
            that serves as the initial condition for the phase field evolution.
        """
        shape = (
            domain.N_spatial,
            domain.N_spatial,
            domain.N_spatial,
            domain.N_phase,
            domain.N_phase,
            domain.N_phase,
            domain.N_temporal,
        )

        # Create Gaussian source in spatial dimensions
        x = np.linspace(-domain.L_spatial / 2, domain.L_spatial / 2, domain.N_spatial)
        X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
        r_squared = X**2 + Y**2 + Z**2

        # Localization width controlled by eta
        width = 1.0 / (1.0 + eta)

        # Create 7D source with spatial localization
        source = np.zeros(shape, dtype=complex)

        # Apply spatial step function envelope
        spatial_envelope = self._step_resonator_spatial_envelope(r_squared, width)

        # Broadcast to 7D
        for phi1 in range(domain.N_phase):
            for phi2 in range(domain.N_phase):
                for phi3 in range(domain.N_phase):
                    for t in range(domain.N_temporal):
                        # Add phase modulation
                        phase = phi1 + phi2 + phi3
                        source[:, :, :, phi1, phi2, phi3, t] = (
                            spatial_envelope * np.exp(1j * phase)
                        )

        return source

    def _rank_parameters(
        self, sobol_indices: Dict[str, Any]
    ) -> List[Tuple[str, float]]:
        """
        Rank parameters by their total-order Sobol indices.

        Args:
            sobol_indices: Dictionary with Sobol indices

        Returns:
            List of (parameter_name, total_order_index) tuples sorted by importance
        """
        ranking = []

        for param_name, indices in sobol_indices.items():
            total_order = indices["total_order"]
            ranking.append((param_name, total_order))

        # Sort by total-order index (descending)
        ranking.sort(key=lambda x: x[1], reverse=True)

        return ranking

    def _compute_stability_metrics(
        self, sobol_indices: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute stability metrics for sensitivity analysis.

        Physical Meaning:
            Evaluates the stability and reliability of the sensitivity
            analysis results, including convergence and consistency checks.
        """
        # Extract total-order indices
        total_indices = [indices["total_order"] for indices in sobol_indices.values()]

        # Compute stability metrics
        total_sensitivity = np.sum(total_indices)
        max_sensitivity = np.max(total_indices)
        min_sensitivity = np.min(total_indices)

        # Check for convergence (total sensitivity should be close to 1)
        convergence_metric = abs(total_sensitivity - 1.0)

        # Check for parameter dominance
        dominance_ratio = (
            max_sensitivity / min_sensitivity if min_sensitivity > 0 else float("inf")
        )

        return {
            "total_sensitivity": total_sensitivity,
            "max_sensitivity": max_sensitivity,
            "min_sensitivity": min_sensitivity,
            "convergence_metric": convergence_metric,
            "dominance_ratio": dominance_ratio,
            "is_converged": convergence_metric < 0.1,
            "is_balanced": dominance_ratio < 10.0,
        }

    def _step_resonator_spatial_envelope(
        self, r_squared: np.ndarray, width: float
    ) -> np.ndarray:
        """
        Step resonator spatial envelope according to 7D BVP theory.

        Physical Meaning:
            Implements step function spatial envelope instead of Gaussian envelope
            according to 7D BVP theory principles where spatial boundaries
            are determined by step functions rather than smooth transitions.

        Mathematical Foundation:
            Envelope = Θ(width_cutoff - r) where Θ is the Heaviside step function
            and width_cutoff is the cutoff radius for the spatial envelope.

        Args:
            r_squared (np.ndarray): Squared radial distance.
            width (float): Spatial width parameter.

        Returns:
            np.ndarray: Step function spatial envelope according to 7D BVP theory.
        """
        # Step function spatial envelope according to 7D BVP theory
        cutoff_radius_squared = width**2
        transmission_coeff = 1.0

        # Apply step function boundary condition
        envelope = transmission_coeff * np.where(
            r_squared < cutoff_radius_squared, 1.0, 0.0
        )

        return envelope
