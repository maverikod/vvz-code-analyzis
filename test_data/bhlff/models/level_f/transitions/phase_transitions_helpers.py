"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase transitions helper methods.

This module implements helper methods for phase transitions operations
that support the main PhaseTransitionsCore class with full 7D BVP theory
implementations.

Physical Meaning:
    Provides helper methods for phase transitions including
    particle energy computation, particle coupling computation,
    and 7D BVP theory effects.

Mathematical Foundation:
    Implements helper methods for:
    - Particle energy computation according to 7D BVP theory
    - Particle coupling computation according to 7D BVP theory
    - 7D BVP theory effects and interactions

Example:
    >>> helpers = PhaseTransitionsHelpers(config)
    >>> energy = helpers.compute_particle_energy_7d_bvp(local_field, particle)
"""

import numpy as np
from typing import Dict, Any


class PhaseTransitionsHelpers:
    """
    Helper methods for phase transitions operations.

    Physical Meaning:
        Provides helper methods for phase transitions including
        particle energy computation, particle coupling computation,
        and 7D BVP theory effects.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize phase transitions helpers.

        Args:
            config (Dict[str, Any]): Phase transitions configuration parameters.
        """
        self.config = config

    def compute_particle_energy_7d_bvp(self, local_field: complex, particle) -> float:
        """
        Compute particle energy according to 7D BVP theory.

        Physical Meaning:
            Computes particle energy from local field configuration
            according to 7D BVP theory principles.

        Args:
            local_field (complex): Local field value at particle position.
            particle: Particle object to update.

        Returns:
            float: Particle energy according to 7D BVP theory.
        """
        # Compute energy from field amplitude and phase
        amplitude = np.abs(local_field)
        phase = np.angle(local_field)

        # Apply 7D BVP energy computation
        kinetic_energy = 0.5 * amplitude**2
        potential_energy = 0.25 * amplitude**4
        phase_energy = 0.5 * phase**2

        # Total energy according to 7D BVP theory
        total_energy = kinetic_energy + potential_energy + phase_energy

        return total_energy

    def compute_particle_coupling_7d_bvp(self, local_field: complex, particle) -> float:
        """
        Compute particle coupling according to 7D BVP theory.

        Physical Meaning:
            Computes particle coupling strength from local field configuration
            according to 7D BVP theory principles.

        Args:
            local_field (complex): Local field value at particle position.
            particle: Particle object to update.

        Returns:
            float: Particle coupling strength according to 7D BVP theory.
        """
        # Compute coupling from field properties
        amplitude = np.abs(local_field)
        phase = np.angle(local_field)

        # Apply 7D BVP coupling computation
        amplitude_coupling = amplitude**2
        phase_coupling = np.cos(phase) ** 2

        # Total coupling according to 7D BVP theory
        total_coupling = amplitude_coupling * phase_coupling

        return total_coupling

    def compute_field_energy_7d_bvp(self, field: np.ndarray) -> float:
        """
        Compute field energy according to 7D BVP theory.

        Physical Meaning:
            Computes total field energy from field configuration
            according to 7D BVP theory principles.

        Args:
            field (np.ndarray): Field configuration.

        Returns:
            float: Total field energy according to 7D BVP theory.
        """
        # Compute field energy components
        amplitude = np.abs(field)
        phase = np.angle(field)

        # Apply 7D BVP energy computation
        kinetic_energy = 0.5 * np.sum(amplitude**2)
        potential_energy = 0.25 * np.sum(amplitude**4)
        phase_energy = 0.5 * np.sum(phase**2)

        # Total energy according to 7D BVP theory
        total_energy = kinetic_energy + potential_energy + phase_energy

        return total_energy

    def compute_field_coupling_7d_bvp(self, field: np.ndarray) -> float:
        """
        Compute field coupling according to 7D BVP theory.

        Physical Meaning:
            Computes total field coupling strength from field configuration
            according to 7D BVP theory principles.

        Args:
            field (np.ndarray): Field configuration.

        Returns:
            float: Total field coupling strength according to 7D BVP theory.
        """
        # Compute field coupling components
        amplitude = np.abs(field)
        phase = np.angle(field)

        # Apply 7D BVP coupling computation
        amplitude_coupling = np.sum(amplitude**2)
        phase_coupling = np.sum(np.cos(phase) ** 2)

        # Total coupling according to 7D BVP theory
        total_coupling = amplitude_coupling * phase_coupling

        return total_coupling

    def compute_nonlinear_interaction_7d_bvp(self, field: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear interaction term according to 7D BVP theory.

        Physical Meaning:
            Computes nonlinear interaction term from field configuration
            according to 7D BVP theory principles.

        Args:
            field (np.ndarray): Field configuration.

        Returns:
            np.ndarray: Nonlinear interaction term according to 7D BVP theory.
        """
        # Compute nonlinear interaction according to 7D BVP theory
        amplitude = np.abs(field)
        phase = np.angle(field)

        # Apply 7D BVP nonlinear interaction
        nonlinear_term = field * amplitude**2 * np.exp(1j * phase)

        return nonlinear_term

    def compute_phase_coherence_7d_bvp(self, field: np.ndarray) -> float:
        """
        Compute phase coherence according to 7D BVP theory.

        Physical Meaning:
            Computes phase coherence from field configuration
            according to 7D BVP theory principles.

        Args:
            field (np.ndarray): Field configuration.

        Returns:
            float: Phase coherence according to 7D BVP theory.
        """
        # Compute phase coherence according to 7D BVP theory
        phase = np.angle(field)
        amplitude = np.abs(field)

        # Apply 7D BVP phase coherence computation
        phase_coherence = np.sum(amplitude * np.cos(phase)) / np.sum(amplitude)

        return phase_coherence

    def compute_amplitude_coherence_7d_bvp(self, field: np.ndarray) -> float:
        """
        Compute amplitude coherence according to 7D BVP theory.

        Physical Meaning:
            Computes amplitude coherence from field configuration
            according to 7D BVP theory principles.

        Args:
            field (np.ndarray): Field configuration.

        Returns:
            float: Amplitude coherence according to 7D BVP theory.
        """
        # Compute amplitude coherence according to 7D BVP theory
        amplitude = np.abs(field)

        # Apply 7D BVP amplitude coherence computation
        amplitude_coherence = np.std(amplitude) / np.mean(amplitude)

        return amplitude_coherence
