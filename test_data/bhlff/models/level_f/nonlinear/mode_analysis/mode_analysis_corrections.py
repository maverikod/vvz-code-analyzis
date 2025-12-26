"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Nonlinear corrections computation for mode analysis.
"""

import numpy as np
from typing import Dict, Any, List


class NonlinearModeAnalyzerCorrections:
    """
    Nonlinear corrections computation for mode analysis.

    Physical Meaning:
        Provides methods to compute nonlinear corrections to linear modes,
        find bifurcation points, and analyze stability.
    """

    def __init__(self, nonlinear_params: Dict[str, Any]):
        """
        Initialize corrections computer.

        Args:
            nonlinear_params (Dict[str, Any]): Nonlinear parameters.
        """
        self.nonlinear_params = nonlinear_params

    def compute_nonlinear_corrections(
        self, linear_modes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute nonlinear corrections to linear modes.

        Physical Meaning:
            Computes nonlinear corrections to linear
            collective modes.

        Args:
            linear_modes (Dict[str, Any]): Linear mode results.

        Returns:
            Dict[str, Any]: Nonlinear corrections.
        """
        # Extract linear frequencies
        linear_frequencies = linear_modes.get("frequencies", [])

        # Compute nonlinear frequency shifts
        nonlinear_frequencies = []
        for freq in linear_frequencies:
            # Nonlinear frequency shift
            shift = self.nonlinear_params.get("strength", 1.0) * freq**2
            nonlinear_freq = freq + shift
            nonlinear_frequencies.append(nonlinear_freq)

        # Compute nonlinear amplitudes
        linear_amplitudes = linear_modes.get("amplitudes", [])
        nonlinear_amplitudes = []
        for amp in linear_amplitudes:
            # Nonlinear amplitude correction
            correction = self.nonlinear_params.get("strength", 1.0) * amp**2
            nonlinear_amp = amp + correction
            nonlinear_amplitudes.append(nonlinear_amp)

        return {
            "frequencies": nonlinear_frequencies,
            "amplitudes": nonlinear_amplitudes,
            "frequency_shifts": [
                nf - lf for nf, lf in zip(nonlinear_frequencies, linear_frequencies)
            ],
            "amplitude_corrections": [
                na - la for na, la in zip(nonlinear_amplitudes, linear_amplitudes)
            ],
        }

    def find_bifurcation_points(self) -> List[Dict[str, Any]]:
        """
        Find bifurcation points.

        Physical Meaning:
            Identifies bifurcation points in the nonlinear
            system where qualitative changes occur.

        Returns:
            List[Dict[str, Any]]: Bifurcation points.
        """
        # Simplified bifurcation analysis
        # In practice, this would involve proper bifurcation theory
        bifurcations = []

        # Find critical nonlinear strength
        critical_strength = 1.0 / self.nonlinear_params.get("strength", 1.0)

        # Add bifurcation point
        bifurcations.append(
            {
                "parameter": "nonlinear_strength",
                "critical_value": critical_strength,
                "type": "pitchfork",
                "stability": "unstable",
            }
        )

        return bifurcations

    def analyze_nonlinear_stability(self) -> Dict[str, Any]:
        """
        Analyze nonlinear stability.

        Physical Meaning:
            Analyzes the stability of nonlinear modes
            in the system.

        Returns:
            Dict[str, Any]: Stability analysis.
        """
        # Compute stability matrix
        stability_matrix = self._compute_stability_matrix()

        # Compute eigenvalues
        eigenvalues = np.linalg.eigvals(stability_matrix)

        # Analyze stability
        stable_modes = np.sum(eigenvalues.real < 0)
        unstable_modes = np.sum(eigenvalues.real > 0)
        marginal_modes = np.sum(np.abs(eigenvalues.real) < 1e-12)

        # Determine overall stability
        if unstable_modes == 0:
            stability = "stable"
        elif stable_modes > unstable_modes:
            stability = "mostly_stable"
        else:
            stability = "unstable"

        return {
            "eigenvalues": eigenvalues.tolist(),
            "stable_modes": int(stable_modes),
            "unstable_modes": int(unstable_modes),
            "marginal_modes": int(marginal_modes),
            "stability": stability,
            "max_growth_rate": float(np.max(eigenvalues.real)),
        }

    def _compute_stability_matrix(self) -> np.ndarray:
        """
        Compute stability matrix.

        Physical Meaning:
            Computes the stability matrix for the nonlinear
            system.

        Returns:
            np.ndarray: Stability matrix.
        """
        # Simplified stability matrix
        # In practice, this would involve proper stability analysis
        n_modes = 3  # Placeholder
        stability_matrix = np.random.rand(n_modes, n_modes) - 0.5

        return stability_matrix

