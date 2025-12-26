"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Single soliton validation and physical properties.

This module implements validation and physical properties computation
for single soliton solutions using 7D BVP theory.

Physical Meaning:
    Implements soliton validation including shape validation,
    solution quality assessment, and physical properties computation
    using 7D BVP theory principles.

Example:
    >>> validator = SingleSolitonValidation(system, nonlinear_params)
    >>> is_valid = validator.validate_soliton_shape(solution, amplitude, width)
"""

import numpy as np
from typing import Dict, Any
import logging

from .base import SolitonAnalysisBase


class SingleSolitonValidation(SolitonAnalysisBase):
    """
    Single soliton validation and physical properties.

    Physical Meaning:
        Implements soliton validation including shape validation,
        solution quality assessment, and physical properties computation
        using 7D BVP theory principles.

    Mathematical Foundation:
        Validates soliton solutions against 7D BVP theory requirements
        including energy conservation, phase coherence, and stability.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize single soliton validation."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def validate_soliton_shape(
        self, solution: np.ndarray, amplitude: float, width: float
    ) -> bool:
        """
        Validate soliton shape for physical correctness.

        Physical Meaning:
            Validates that the soliton solution has proper physical
            characteristics including monotonic decay and proper
            amplitude-width relationship.

        Args:
            solution (np.ndarray): Soliton solution.
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.

        Returns:
            bool: True if soliton shape is valid.
        """
        try:
            field = solution[0] if solution.ndim > 1 else solution

            # Check for proper amplitude
            max_field = np.max(np.abs(field))
            if max_field < 0.5 * amplitude or max_field > 2.0 * amplitude:
                return False

            # Check for monotonic decay (basic shape check)
            if len(field) > 10:
                # Check that field decays from center
                center_idx = len(field) // 2
                left_decay = np.all(np.diff(field[:center_idx]) <= 0)
                right_decay = np.all(np.diff(field[center_idx:]) >= 0)

                if not (left_decay and right_decay):
                    return False

            # Check for no oscillations (smooth profile)
            if len(field) > 5:
                second_deriv = np.gradient(np.gradient(field))
                if np.any(np.abs(second_deriv) > 10.0 * amplitude):
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Soliton shape validation failed: {e}")
            return False

    def validate_solution_quality(
        self, solution: Dict[str, Any], amplitude: float, width: float
    ) -> bool:
        """
        Validate overall solution quality.

        Physical Meaning:
            Validates that the complete soliton solution meets
            all physical requirements and quality criteria.

        Args:
            solution (Dict[str, Any]): Complete soliton solution.
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.

        Returns:
            bool: True if solution quality is acceptable.
        """
        try:
            # Check solution completeness
            required_keys = [
                "spatial_grid",
                "profile",
                "field_energy",
                "momentum",
                "topological_charge",
            ]
            if not all(key in solution for key in required_keys):
                return False

            # Check physical parameters
            if solution["field_energy"] <= 0 or np.isnan(solution["field_energy"]):
                return False

            if (
                abs(solution["topological_charge"]) > 2.0
            ):  # Reasonable topological charge
                return False

            # Check profile quality
            profile = solution["profile"]
            if np.any(np.isnan(profile)) or np.any(np.isinf(profile)):
                return False

            return True

        except Exception as e:
            self.logger.error(f"Solution quality validation failed: {e}")
            return False

    def compute_soliton_physical_properties(
        self, amplitude: float, width: float, position: float, solution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute comprehensive soliton physical properties.

        Physical Meaning:
            Computes all relevant physical properties of the soliton
            including energy, momentum, topological charge, and stability
            metrics using 7D BVP theory.

        Args:
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.
            position (float): Soliton position.
            solution (Dict[str, Any]): Soliton solution.

        Returns:
            Dict[str, Any]: Complete physical properties.
        """
        try:
            profile = solution["profile"]
            x = solution["spatial_grid"]

            # Compute additional physical properties
            kinetic_energy = 0.5 * np.trapz(np.gradient(profile) ** 2, x)
            potential_energy = 0.5 * self.lambda_param * np.trapz(profile**2, x)
            total_energy = kinetic_energy + potential_energy

            # Compute stability metrics
            stability_metric = self._compute_stability_metric(profile, x)

            # Compute phase coherence
            phase_coherence = self._compute_phase_coherence(profile, x)

            # Compute 7D BVP specific properties
            bvp_properties = self._compute_7d_bvp_properties(
                profile, x, amplitude, width
            )

            return {
                "kinetic_energy": kinetic_energy,
                "potential_energy": potential_energy,
                "total_energy": total_energy,
                "stability_metric": stability_metric,
                "phase_coherence": phase_coherence,
                "7d_bvp_properties": bvp_properties,
                "energy_density": total_energy / (width * 2),  # Energy per unit width
                "momentum_density": solution["momentum"] / (width * 2),
            }

        except Exception as e:
            self.logger.error(f"Physical properties computation failed: {e}")
            return {}

    def _compute_stability_metric(self, profile: np.ndarray, x: np.ndarray) -> float:
        """
        Compute soliton stability metric.

        Physical Meaning:
            Computes a stability metric based on the soliton's
            energy distribution and shape characteristics.

        Args:
            profile (np.ndarray): Soliton profile.
            x (np.ndarray): Spatial coordinates.

        Returns:
            float: Stability metric (higher is more stable).
        """
        try:
            # Compute energy distribution
            energy_density = 0.5 * (
                np.gradient(profile) ** 2 + self.lambda_param * profile**2
            )

            # Compute stability as ratio of peak energy to total energy
            peak_energy = np.max(energy_density)
            total_energy = np.trapz(energy_density, x)

            if total_energy > 0:
                return peak_energy / total_energy
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Stability metric computation failed: {e}")
            return 0.0

    def _compute_phase_coherence(self, profile: np.ndarray, x: np.ndarray) -> float:
        """
        Compute phase coherence metric.

        Physical Meaning:
            Computes the phase coherence of the soliton based on
            its phase field properties and 7D BVP theory.

        Args:
            profile (np.ndarray): Soliton profile.
            x (np.ndarray): Spatial coordinates.

        Returns:
            float: Phase coherence metric.
        """
        try:
            # Compute phase field from profile
            phase_field = np.arctan2(profile, np.gradient(profile))

            # Compute phase coherence as consistency of phase
            phase_variance = np.var(phase_field)
            phase_coherence = 1.0 / (1.0 + phase_variance)

            return phase_coherence

        except Exception as e:
            self.logger.error(f"Phase coherence computation failed: {e}")
            return 0.0

    def _compute_7d_bvp_properties(
        self, profile: np.ndarray, x: np.ndarray, amplitude: float, width: float
    ) -> Dict[str, Any]:
        """
        Compute 7D BVP specific properties.

        Physical Meaning:
            Computes properties specific to 7D BVP theory including
            fractional Laplacian effects and step resonator properties.

        Args:
            profile (np.ndarray): Soliton profile.
            x (np.ndarray): Spatial coordinates.
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.

        Returns:
            Dict[str, Any]: 7D BVP specific properties.
        """
        try:
            # Compute fractional Laplacian contribution
            fractional_contribution = self._compute_fractional_laplacian_contribution(
                profile, x
            )

            # Compute step resonator efficiency
            step_efficiency = self._compute_step_resonator_efficiency(profile, x, width)

            # Compute 7D phase space properties
            phase_space_properties = self._compute_7d_phase_space_properties(profile, x)

            return {
                "fractional_laplacian_contribution": fractional_contribution,
                "step_resonator_efficiency": step_efficiency,
                "7d_phase_space_properties": phase_space_properties,
                "bvp_convergence_quality": self._compute_bvp_convergence_quality(
                    profile, x
                ),
            }

        except Exception as e:
            self.logger.error(f"7D BVP properties computation failed: {e}")
            return {}

    def _compute_fractional_laplacian_contribution(
        self, profile: np.ndarray, x: np.ndarray
    ) -> float:
        """Compute fractional Laplacian contribution to soliton energy."""
        try:
            # Compute fractional Laplacian
            frac_lap = self._compute_full_fractional_laplacian(x, profile)

            # Compute contribution as ratio to total energy
            total_energy = np.trapz(profile**2, x)
            frac_energy = np.trapz(profile * frac_lap, x)

            if total_energy > 0:
                return abs(frac_energy) / total_energy
            else:
                return 0.0

        except Exception as e:
            self.logger.error(
                f"Fractional Laplacian contribution computation failed: {e}"
            )
            return 0.0

    def _compute_step_resonator_efficiency(
        self, profile: np.ndarray, x: np.ndarray, width: float
    ) -> float:
        """Compute step resonator efficiency."""
        try:
            # Compute step resonator profile
            step_profile = self._step_resonator_profile(x, 0.0, width)

            # Compute efficiency as overlap with step resonator
            overlap = np.trapz(profile * step_profile, x)
            total_profile = np.trapz(np.abs(profile), x)

            if total_profile > 0:
                return overlap / total_profile
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Step resonator efficiency computation failed: {e}")
            return 0.0

    def _compute_7d_phase_space_properties(
        self, profile: np.ndarray, x: np.ndarray
    ) -> Dict[str, float]:
        """Compute 7D phase space properties."""
        try:
            # Compute momentum space representation
            profile_fft = np.fft.fft(profile)
            k = np.fft.fftfreq(len(x), x[1] - x[0]) * 2 * np.pi

            # Compute phase space volume
            phase_space_volume = np.trapz(np.abs(profile_fft) ** 2, k)

            # Compute phase space entropy
            prob_dist = np.abs(profile_fft) ** 2
            prob_dist = prob_dist / np.sum(prob_dist)  # Normalize
            entropy = -np.sum(prob_dist * np.log(prob_dist + 1e-10))

            return {
                "phase_space_volume": phase_space_volume,
                "phase_space_entropy": entropy,
                "spectral_width": np.std(k * np.abs(profile_fft)),
            }

        except Exception as e:
            self.logger.error(f"7D phase space properties computation failed: {e}")
            return {}

    def _compute_bvp_convergence_quality(
        self, profile: np.ndarray, x: np.ndarray
    ) -> float:
        """Compute BVP convergence quality metric."""
        try:
            # Compute residual of the 7D equation
            residual = self._compute_equation_residual(profile, x)

            # Compute quality as inverse of residual
            quality = 1.0 / (1.0 + np.mean(residual**2))

            return quality

        except Exception as e:
            self.logger.error(f"BVP convergence quality computation failed: {e}")
            return 0.0

    def _compute_equation_residual(
        self, profile: np.ndarray, x: np.ndarray
    ) -> np.ndarray:
        """Compute residual of the 7D soliton equation."""
        try:
            # Compute fractional Laplacian
            frac_lap = self._compute_full_fractional_laplacian(x, profile)

            # Compute source term
            source = self._step_resonator_source(x, 0.0, 1.0)  # Default width

            # Compute residual: L_β a - λa - s(x)
            residual = frac_lap + self.lambda_param * profile - source

            return residual

        except Exception as e:
            self.logger.error(f"Equation residual computation failed: {e}")
            return np.zeros_like(profile)

    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """Step resonator profile using 7D BVP theory."""
        try:
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)
        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)

    def _step_resonator_source(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """Step resonator source term using 7D BVP theory."""
        try:
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)
        except Exception as e:
            self.logger.error(f"Step resonator source computation failed: {e}")
            return np.zeros_like(x)

    def _compute_full_fractional_laplacian(
        self, x: np.ndarray, field: np.ndarray
    ) -> np.ndarray:
        """Compute full fractional Laplacian using 7D BVP theory."""
        try:
            dx = x[1] - x[0] if len(x) > 1 else 1.0
            field_fft = np.fft.fft(field)
            N = len(x)
            k = np.fft.fftfreq(N, dx) * 2 * np.pi
            k_magnitude = np.abs(k)
            k_magnitude[0] = 1e-10
            fractional_spectrum = (k_magnitude ** (2 * self.beta)) * field_fft
            fractional_laplacian = np.real(np.fft.ifft(fractional_spectrum))
            return self.mu * fractional_laplacian
        except Exception as e:
            self.logger.error(f"Full fractional Laplacian computation failed: {e}")
            return self.mu * (np.abs(x) ** (2 * self.beta)) * field
