"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Dispersion analysis for collective excitations.

This module implements dispersion analysis functionality for
collective excitations in multi-particle systems.

Theoretical Background:
    Dispersion analysis involves computing ω(k) relations
    for collective excitations in the system, revealing
    the relationship between frequency and wave vector.

Example:
    >>> analyzer = DispersionAnalyzer(system)
    >>> dispersion = analyzer.compute_dispersion_relations()
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from ...base.abstract_model import AbstractModel


class DispersionAnalyzer(AbstractModel):
    """
    Dispersion analysis for collective excitations.

    Physical Meaning:
        Analyzes dispersion relations ω(k) for collective
        excitations in multi-particle systems.

    Mathematical Foundation:
        Implements dispersion analysis using the relationship
        between frequency and wave vector for collective modes.

    Attributes:
        system: Multi-particle system
        k_max: Maximum wave vector
        n_k_points: Number of k points
    """

    def __init__(self, system: "MultiParticleSystem"):
        """
        Initialize dispersion analyzer.

        Physical Meaning:
            Sets up the dispersion analyzer for studying
            dispersion relations in the multi-particle system.

        Args:
            system (MultiParticleSystem): Multi-particle system
        """
        super().__init__(system.domain)
        self.system = system

        # Setup analysis parameters
        self._setup_analysis_parameters()

    def compute_dispersion_relations(self) -> Dict[str, Any]:
        """
        Compute dispersion relations for collective modes.

        Physical Meaning:
            Calculates ω(k) relations for collective
            excitations in the system.

        Returns:
            Dict containing:
                - wave_vectors: k (wave vector magnitudes)
                - frequencies: ω(k) (dispersion relation)
                - group_velocities: v_g = dω/dk
                - phase_velocities: v_φ = ω/k
        """
        # Create wave vector grid
        k_values = np.linspace(0, self.k_max, self.n_k_points)

        # Compute frequencies for each k
        frequencies = []
        group_velocities = []
        phase_velocities = []

        for k in k_values:
            # Solve dispersion equation
            omega = self._solve_dispersion_equation(k)
            frequencies.append(omega)

            # Compute group velocity
            v_g = self._compute_group_velocity(k, omega)
            group_velocities.append(v_g)

            # Compute phase velocity
            v_phi = omega / k if k > 0 else 0
            phase_velocities.append(v_phi)

        # Fit dispersion relation
        frequencies_array = np.array(frequencies)
        dispersion_fit = self._fit_dispersion_relation(k_values, frequencies_array)

        return {
            "k_values": k_values,
            "frequencies": np.array(frequencies),
            "group_velocities": np.array(group_velocities),
            "phase_velocities": np.array(phase_velocities),
            "dispersion_fit": dispersion_fit,
        }

    def compute_susceptibility(self, frequencies: np.ndarray) -> np.ndarray:
        """
        Compute susceptibility function χ(ω).

        Physical Meaning:
            Calculates the linear response susceptibility
            for collective excitations.

        Args:
            frequencies (np.ndarray): Frequency array

        Returns:
            np.ndarray: Susceptibility χ(ω)
        """
        # Get collective modes
        modes = self.system.find_collective_modes()
        mode_frequencies = modes.get("frequencies", modes.get("mode_frequencies", []))
        mode_amplitudes = modes.get("amplitudes", modes.get("mode_amplitudes", []))
        mode_frequencies = np.asarray(mode_frequencies, dtype=float)
        mode_amplitudes = np.asarray(mode_amplitudes, dtype=float)

        # Compute susceptibility
        susceptibility = np.zeros_like(frequencies, dtype=complex)

        for i, (omega_n, A_n) in enumerate(zip(mode_frequencies, mode_amplitudes)):
            # 7D BVP response without damping
            susceptibility += A_n / (omega_n**2 - frequencies**2)

        return susceptibility

    def _setup_analysis_parameters(self) -> None:
        """
        Setup analysis parameters for dispersion analysis.

        Physical Meaning:
            Initializes parameters needed for dispersion
            relation analysis.
        """
        self.k_max = 10.0  # Maximum wave vector
        self.n_k_points = 100  # Number of k points

    def _solve_dispersion_equation(self, k: float) -> float:
        """
        Solve dispersion equation for given wave vector.

        Physical Meaning:
            Solves the dispersion equation ω²(k) = ω₀² + c²k²
            for the given wave vector k.
        """
        # Get system parameters
        modes = self.system.find_collective_modes()
        freqs = modes.get("frequencies")
        if freqs is None:
            freqs = modes.get("mode_frequencies", [])
        freqs = np.asarray(freqs, dtype=float)
        base_frequency = float(np.mean(freqs)) if freqs.size > 0 else 0.0

        # Dispersion relation: ω² = ω₀² + c²k²
        c = 1.0  # Sound speed
        omega_squared = (2 * np.pi * base_frequency) ** 2 + c**2 * k**2

        return np.sqrt(omega_squared) / (2 * np.pi)

    def _compute_group_velocity(self, k: float, omega: float) -> float:
        """
        Compute group velocity v_g = dω/dk.

        Physical Meaning:
            Calculates the group velocity for the
            given wave vector and frequency.
        """
        # Numerical derivative
        dk = 0.01
        omega_plus = self._solve_dispersion_equation(k + dk)
        omega_minus = self._solve_dispersion_equation(k - dk)

        v_g = (omega_plus - omega_minus) / (2 * dk)

        return v_g

    def _fit_dispersion_relation(
        self, k_values: np.ndarray, frequencies: np.ndarray
    ) -> Dict[str, Any]:
        """
        Fit dispersion relation to computed data.

        Physical Meaning:
            Fits the dispersion relation ω²(k) = ω₀² + c²k²
            to the computed frequency data.
        """
        # Fit quadratic relation
        frequencies = np.array(frequencies)
        omega_squared = (2 * np.pi * frequencies) ** 2
        p = np.polyfit(k_values, omega_squared, 1)

        # Extract parameters
        omega_0_squared = p[1]  # Intercept
        c_squared = p[0]  # Slope

        # Clamp numerical artifacts to avoid invalid sqrt
        omega_0 = np.sqrt(max(0.0, float(omega_0_squared))) / (2 * np.pi)
        c = np.sqrt(max(0.0, float(c_squared)))

        # Compute R²
        omega_fit = np.sqrt(np.maximum(0.0, omega_0_squared + c_squared * k_values)) / (
            2 * np.pi
        )
        r_squared = 1 - np.sum((frequencies - omega_fit) ** 2) / np.sum(
            (frequencies - np.mean(frequencies)) ** 2
        )

        return {"omega_0": omega_0, "c": c, "r_squared": r_squared, "coefficients": p}

    def analyze(self, data: Any) -> Dict[str, Any]:
        """
        Analyze dispersion by computing ω(k) relations.

        Args:
            data (Any): Unused placeholder for interface compliance.

        Returns:
            Dict[str, Any]: Dispersion analysis results.
        """
        return self.compute_dispersion_relations()
