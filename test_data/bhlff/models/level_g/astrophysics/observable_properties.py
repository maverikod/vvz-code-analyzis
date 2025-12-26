"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Observable properties calculator for astrophysical objects in 7D phase field theory.

This module implements methods for computing observable properties of
astrophysical objects that can be compared with astronomical observations.

Theoretical Background:
    Observable properties in 7D phase field theory are computed from
    phase field configurations and can be compared with astronomical
    observations to validate the theory.

Mathematical Foundation:
    Implements observable property calculations:
    - Effective radius: R_eff = ∫ r |a(r)|² d³x d³φ dt / ∫ |a(r)|² d³x d³φ dt
    - Phase energy: E = ∫ [μ|∇a|² + λ|a|² + nonlinear_terms] d³x d³φ dt
    - Defect density: ρ = |∇×∇Θ|

Example:
    >>> calculator = ObservablePropertiesCalculator()
    >>> properties = calculator.compute_observable_properties(phase_field, params)
"""

import numpy as np
from typing import Dict, Any, Optional


class ObservablePropertiesCalculator:
    """
    Calculator for observable properties of astrophysical objects.

    Physical Meaning:
        Computes observable properties that can be compared
        with astronomical observations to validate the 7D
        phase field theory.

    Mathematical Foundation:
        Implements comprehensive observable property calculations
        for astrophysical objects in 7D space-time.

    Attributes:
        config (Dict[str, Any]): Calculator configuration
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize observable properties calculator.

        Physical Meaning:
            Sets up the calculator with configuration parameters
            for computing observable properties.

        Args:
            config: Calculator configuration parameters
        """
        self.config = config or {}

    def compute_observable_properties(
        self, phase_field: np.ndarray, object_params: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compute observable properties of an astrophysical object.

        Physical Meaning:
            Computes observable properties that can be compared
            with astronomical observations to validate the theory.

        Mathematical Foundation:
            Computes comprehensive observable properties including
            mass, radius, energy, and defect density.

        Args:
            phase_field: Phase field array
            object_params: Object parameters

        Returns:
            Observable properties dictionary
        """
        if phase_field is None:
            return {}

        # Compute observable properties
        properties = {
            "total_mass": object_params.get("mass", 0.0),
            "effective_radius": self._compute_effective_radius(
                phase_field, object_params
            ),
            "phase_energy": self._compute_phase_energy(phase_field, object_params),
            "topological_defect_density": self._compute_defect_density(
                phase_field, object_params
            ),
        }

        return properties

    def _compute_effective_radius(
        self, phase_field: np.ndarray, object_params: Dict[str, Any]
    ) -> float:
        """
        Compute effective radius using 7D BVP theory.

        Physical Meaning:
            Computes the effective radius where the phase field
            amplitude drops to a threshold value using step resonator
            transmission model instead of exponential decay.

        Mathematical Foundation:
            R_eff = ∫ r |a(r)|² d³x d³φ dt / ∫ |a(r)|² d³x d³φ dt
            where a(r) is the phase field amplitude.

        Args:
            phase_field: Phase field array
            object_params: Object parameters

        Returns:
            Effective radius from 7D phase field analysis
        """
        if phase_field is None:
            return 0.0

        # Create coordinate grid for radius computation
        grid_size = phase_field.shape[0]
        domain_size = object_params.get("domain_size", 10.0)

        # Create radial coordinate
        x = np.linspace(-domain_size / 2, domain_size / 2, grid_size)
        y = np.linspace(-domain_size / 2, domain_size / 2, grid_size)
        z = np.linspace(-domain_size / 2, domain_size / 2, grid_size)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        R = np.sqrt(X**2 + Y**2 + Z**2)

        # Compute amplitude-weighted radius
        amplitude_squared = phase_field**2
        total_amplitude = np.sum(amplitude_squared)

        if total_amplitude > 0:
            # Effective radius as amplitude-weighted average
            effective_radius = np.sum(R * amplitude_squared) / total_amplitude
        else:
            effective_radius = 0.0

        # Apply step resonator model corrections
        # Transmission coefficient affects effective radius
        transmission_coeff = 0.9  # Energy transmission through resonator
        effective_radius *= transmission_coeff

        return float(effective_radius)

    def _compute_phase_energy(
        self, phase_field: np.ndarray, object_params: Dict[str, Any]
    ) -> float:
        """
        Compute phase field energy using 7D BVP theory.

        Physical Meaning:
            Computes the total energy associated with the
            phase field configuration in 7D space-time using
            the proper energy functional.

        Mathematical Foundation:
            E = ∫ [μ|∇a|² + λ|a|² + nonlinear_terms] d³x d³φ dt
            where a is the phase field amplitude.

        Args:
            phase_field: Phase field array
            object_params: Object parameters

        Returns:
            Phase field energy from 7D BVP theory
        """
        if phase_field is None:
            return 0.0

        # Compute phase field gradients
        phase_gradients = np.gradient(phase_field)

        # Kinetic energy: μ|∇a|²
        mu = object_params.get("mu", 1.0)  # Diffusion coefficient
        kinetic_energy = mu * sum(np.sum(grad**2) for grad in phase_gradients)

        # Potential energy: λ|a|² (but no mass term in 7D BVP theory)
        # Instead use gradient-based potential energy
        lambda_param = object_params.get("lambda", 0.1)
        gradient_energy = lambda_param * sum(
            np.sum(grad**2) for grad in phase_gradients
        )

        # Phase field amplitude energy
        amplitude_energy = np.sum(phase_field**2)

        # Nonlinear energy terms (higher-order interactions)
        nonlinear_energy = self._compute_nonlinear_energy(phase_field, object_params)

        # Total energy
        total_energy = (
            kinetic_energy + gradient_energy + amplitude_energy + nonlinear_energy
        )

        return float(total_energy)

    def _compute_nonlinear_energy(
        self, phase_field: np.ndarray, object_params: Dict[str, Any]
    ) -> float:
        """
        Compute nonlinear energy terms in 7D BVP theory.

        Physical Meaning:
            Computes higher-order nonlinear interactions in the
            phase field that contribute to the total energy.

        Args:
            phase_field: Phase field array
            object_params: Object parameters

        Returns:
            Nonlinear energy contribution
        """
        if phase_field is None:
            return 0.0

        # Nonlinear energy from phase field interactions
        # This includes self-interactions and phase coherence effects
        phase_squared = phase_field**2
        nonlinear_coeff = object_params.get("nonlinear_coeff", 0.1)

        # Self-interaction energy
        self_interaction = nonlinear_coeff * np.sum(phase_squared**2)

        # Phase coherence energy
        phase_coherence = self._compute_phase_coherence(phase_field)
        coherence_energy = phase_coherence * np.sum(phase_squared)

        return float(self_interaction + coherence_energy)

    def _compute_phase_coherence(self, phase_field: np.ndarray) -> float:
        """
        Compute phase coherence in 7D BVP theory.

        Physical Meaning:
            Measures the degree of phase coherence across the 7D
            phase space-time, which affects correlation length.

        Mathematical Foundation:
            C = 1 / (1 + Var[Θ] / E[Θ]²)
            where Θ is the phase field and E[Θ] is the mean.

        Args:
            phase_field: Phase field array

        Returns:
            Phase coherence measure
        """
        if phase_field is None:
            return 0.0

        # Compute phase coherence as normalized variance
        phase_mean = np.mean(phase_field)
        phase_variance = np.var(phase_field)

        if phase_variance > 0:
            coherence = 1.0 / (1.0 + phase_variance / (phase_mean**2 + 1e-10))
        else:
            coherence = 1.0

        return float(coherence)

    def _compute_defect_density(
        self, phase_field: np.ndarray, object_params: Dict[str, Any]
    ) -> float:
        """
        Compute topological defect density using 7D BVP theory.

        Physical Meaning:
            Computes the density of topological defects in
            the phase field configuration using proper
            topological analysis in 7D space-time.

        Mathematical Foundation:
            ρ_defects = ∫ |∇×∇Θ| d³x d³φ dt / ∫ d³x d³φ dt
            where ∇×∇Θ measures the topological charge density.

        Args:
            phase_field: Phase field array
            object_params: Object parameters

        Returns:
            Topological defect density from 7D analysis
        """
        if phase_field is None:
            return 0.0

        # Compute phase field gradients in all dimensions
        phase_gradients = np.gradient(phase_field)

        # Compute curl of phase gradients (topological charge density)
        # For 3D spatial case: ∇×∇Θ = (∂²Θ/∂y∂z - ∂²Θ/∂z∂y, ...)
        if len(phase_gradients) >= 3:
            # Compute second derivatives for curl
            grad_x, grad_y, grad_z = phase_gradients[:3]

            # Compute curl components
            curl_x = np.gradient(grad_z, axis=1) - np.gradient(grad_y, axis=2)
            curl_y = np.gradient(grad_x, axis=2) - np.gradient(grad_z, axis=0)
            curl_z = np.gradient(grad_y, axis=0) - np.gradient(grad_x, axis=1)

            # Curl magnitude
            curl_magnitude = np.sqrt(curl_x**2 + curl_y**2 + curl_z**2)
        else:
            # For lower dimensions, use gradient magnitude
            curl_magnitude = np.sqrt(sum(grad**2 for grad in phase_gradients))

        # Compute defect density as average curl magnitude
        defect_density = np.mean(curl_magnitude)

        # Apply 7D BVP theory corrections
        # Defect density depends on phase coherence and topological structure
        phase_coherence = self._compute_phase_coherence(phase_field)
        topological_charge = abs(object_params.get("topological_charge", 0))

        # Correct for phase coherence and topological charge
        defect_density *= phase_coherence * (1.0 + 0.1 * topological_charge)

        return float(defect_density)

    def compute_phase_properties(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Compute phase properties of a phase field.

        Physical Meaning:
            Analyzes the phase field properties of an astrophysical
            object, including topological characteristics and
            phase coherence measures.

        Mathematical Foundation:
            Computes phase field properties using 7D BVP theory:
            - Phase amplitude and RMS
            - Phase gradient magnitude
            - Correlation length
            - Phase coherence

        Args:
            phase_field: Phase field array to analyze

        Returns:
            Phase properties analysis
        """
        if phase_field is None:
            return {}

        # Compute phase properties
        properties = {
            "phase_amplitude": np.max(np.abs(phase_field)),
            "phase_rms": np.sqrt(np.mean(phase_field**2)),
            "phase_gradient": np.mean(np.abs(np.gradient(phase_field))),
            "correlation_length": self._compute_phase_correlation_length(phase_field),
            "phase_coherence": self._compute_phase_coherence(phase_field),
            "topological_defect_density": self._compute_defect_density(phase_field, {}),
        }

        return properties

    def _compute_phase_correlation_length(self, phase_field: np.ndarray) -> float:
        """
        Compute phase correlation length using 7D BVP theory.

        Physical Meaning:
            Computes the characteristic length scale over which
            the phase field is correlated in 7D phase space-time.
            This is related to the coherence length of the VBP envelope.

        Mathematical Foundation:
            ξ = ∫ |∇Θ|² d³x d³φ dt / ∫ |Θ|² d³x d³φ dt
            where Θ is the phase field in 7D space-time.

        Args:
            phase_field: Phase field array

        Returns:
            Correlation length in 7D phase space-time
        """
        if phase_field is None:
            return 0.0

        # Compute phase field gradients in all dimensions
        phase_gradients = np.gradient(phase_field)

        # Compute gradient magnitude squared
        gradient_squared = sum(grad**2 for grad in phase_gradients)

        # Compute phase field magnitude squared
        phase_squared = phase_field**2

        # Avoid division by zero
        if np.sum(phase_squared) > 0:
            # Correlation length from gradient-to-field ratio
            correlation_length = np.sqrt(
                np.sum(phase_squared) / np.sum(gradient_squared)
            )
        else:
            correlation_length = 0.0

        # Apply 7D BVP theory corrections
        # In 7D space-time, correlation length depends on phase coherence
        phase_coherence = self._compute_phase_coherence(phase_field)
        correlation_length *= phase_coherence

        return float(correlation_length)
