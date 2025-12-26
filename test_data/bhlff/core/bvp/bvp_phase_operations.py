"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP phase operations module.

This module provides phase-related operations for the BVP core,
including phase vector management and electroweak current calculations.

Physical Meaning:
    Implements operations related to the U(1)³ phase structure of the BVP field,
    including phase component management, electroweak current calculations,
    and phase coherence analysis.

Mathematical Foundation:
    Implements operations on the U(1)³ phase vector Θ_a (a=1..3) including:
    - Phase component extraction and combination
    - Electroweak current calculations
    - Phase coherence measurements
    - SU(2) coupling strength management

Example:
    >>> phase_ops = BVPPhaseOperations(phase_vector)
    >>> total_phase = phase_ops.get_total_phase()
    >>> currents = phase_ops.compute_electroweak_currents(envelope)
"""

import numpy as np
from typing import Dict, List

from .phase_vector import PhaseVector


class BVPPhaseOperations:
    """
    Phase operations for BVP core.

    Physical Meaning:
        Provides operations for managing the U(1)³ phase structure
        of the BVP field, including phase component extraction,
        electroweak current calculations, and phase coherence analysis.

    Mathematical Foundation:
        Implements operations on the U(1)³ phase vector Θ_a (a=1..3)
        including phase combination, current calculations, and
        coherence measurements.
    """

    def __init__(self, phase_vector: PhaseVector):
        """
        Initialize phase operations.

        Physical Meaning:
            Sets up phase operations with access to the U(1)³
            phase vector structure.

        Args:
            phase_vector (PhaseVector): U(1)³ phase vector structure.
        """
        self.phase_vector = phase_vector

    def get_phase_components(self) -> List[np.ndarray]:
        """
        Get the three U(1) phase components Θ_a (a=1..3).

        Physical Meaning:
            Returns the three independent U(1) phase components
            that form the U(1)³ structure of the BVP field.

        Returns:
            List[np.ndarray]: List of three phase components Θ_a.
        """
        return self.phase_vector.get_phase_components()

    def get_total_phase(self) -> np.ndarray:
        """
        Get the total phase from U(1)³ structure.

        Physical Meaning:
            Computes the total phase by combining the three
            U(1) components with proper SU(2) coupling.

        Returns:
            np.ndarray: Total phase field.
        """
        return self.phase_vector.get_total_phase()

    def compute_electroweak_currents(
        self, envelope: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents as functionals of the envelope.

        Physical Meaning:
            Computes electromagnetic and weak currents that are
            generated as functionals of the BVP envelope through
            the U(1)³ phase structure.

        Args:
            envelope (np.ndarray): BVP envelope |A|.

        Returns:
            Dict[str, np.ndarray]: Electroweak currents including:
                - em_current: Electromagnetic current
                - weak_current: Weak interaction current
                - mixed_current: Mixed electroweak current
        """
        return self.phase_vector.compute_electroweak_currents(envelope)

    def compute_phase_coherence(self) -> np.ndarray:
        """
        Compute phase coherence measure.

        Physical Meaning:
            Computes a measure of phase coherence across the
            U(1)³ structure, indicating the degree of
            synchronization between the three phase components.

        Returns:
            np.ndarray: Phase coherence measure.
        """
        return self.phase_vector.compute_phase_coherence()

    def get_su2_coupling_strength(self) -> float:
        """
        Get the SU(2) coupling strength.

        Physical Meaning:
            Returns the strength of the weak hierarchical
            coupling to SU(2)/core.

        Returns:
            float: SU(2) coupling strength.
        """
        return self.phase_vector.get_su2_coupling_strength()

    def set_su2_coupling_strength(self, strength: float) -> None:
        """
        Set the SU(2) coupling strength.

        Physical Meaning:
            Updates the strength of the weak hierarchical
            coupling to SU(2)/core.

        Args:
            strength (float): New SU(2) coupling strength.
        """
        self.phase_vector.set_su2_coupling_strength(strength)
