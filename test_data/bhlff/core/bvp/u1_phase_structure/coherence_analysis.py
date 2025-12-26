"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Coherence analysis for U(1)³ phase structure postulate.

This module provides phase coherence analysis functionality for
the U(1)³ phase structure postulate implementation.

Physical Meaning:
    Analyzes phase coherence measures to verify that phase
    relationships are maintained across spatial scales in
    the U(1)³ phase structure.

Mathematical Foundation:
    Computes local and global phase coherence measures
    based on phase gradients and variance analysis.

Example:
    >>> analyzer = CoherenceAnalysis(domain)
    >>> coherence = analyzer.analyze_phase_coherence(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain import Domain


class CoherenceAnalysis:
    """
    Phase coherence analysis for U(1)³ postulate.

    Physical Meaning:
        Analyzes phase coherence measures to verify that phase
        relationships are maintained across spatial scales.

    Mathematical Foundation:
        Computes local and global phase coherence measures
        based on phase gradients and variance analysis.

    Attributes:
        domain (Domain): Computational domain for analysis.
    """

    def __init__(self, domain: Domain) -> None:
        """
        Initialize coherence analysis.

        Physical Meaning:
            Sets up the analyzer with domain information
            for phase coherence analysis.

        Args:
            domain (Domain): Computational domain for analysis.
        """
        self.domain = domain

    def analyze_phase_coherence(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze phase coherence across the field.

        Physical Meaning:
            Computes phase coherence measures to verify that
            phase relationships are maintained across spatial scales.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Phase coherence analysis.
        """
        # Extract phase
        phase = np.angle(envelope)

        # Compute phase coherence measures
        local_coherence = self._compute_local_phase_coherence(phase)
        global_coherence = self._compute_global_phase_coherence(phase)

        # Compute coherence statistics
        mean_local_coherence = np.mean(local_coherence)
        std_local_coherence = np.std(local_coherence)

        return {
            "local_coherence": local_coherence,
            "global_coherence": global_coherence,
            "mean_local_coherence": mean_local_coherence,
            "std_local_coherence": std_local_coherence,
        }

    def _compute_local_phase_coherence(self, phase: np.ndarray) -> np.ndarray:
        """
        Compute local phase coherence.

        Physical Meaning:
            Calculates phase coherence in local neighborhoods
            to measure phase consistency.

        Args:
            phase (np.ndarray): Phase field.

        Returns:
            np.ndarray: Local coherence field.
        """
        # Compute phase gradients
        phase_gradients = []
        for axis in range(3):  # Spatial dimensions only
            gradient = np.gradient(phase, self.domain.dx, axis=axis)
            phase_gradients.append(gradient)

        # Compute gradient magnitude
        gradient_magnitude = np.sqrt(sum(g**2 for g in phase_gradients))

        # Local coherence is inverse of gradient magnitude
        local_coherence = 1.0 / (gradient_magnitude + 1e-12)

        # Normalize
        local_coherence = local_coherence / np.max(local_coherence)

        return local_coherence

    def _compute_global_phase_coherence(self, phase: np.ndarray) -> float:
        """
        Compute global phase coherence.

        Physical Meaning:
            Calculates overall phase coherence across the
            entire field domain.

        Args:
            phase (np.ndarray): Phase field.

        Returns:
            float: Global coherence measure.
        """
        # Compute phase variance
        phase_variance = np.var(phase)

        # Global coherence is inverse of variance
        global_coherence = 1.0 / (phase_variance + 1e-12)

        # Normalize
        global_coherence = min(global_coherence, 1.0)

        return global_coherence

    def __repr__(self) -> str:
        """String representation of coherence analysis."""
        return f"CoherenceAnalysis(domain={self.domain})"
