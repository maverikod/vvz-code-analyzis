"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Mode analysis for ABCD model.

This module implements analysis of resonance modes, including amplitude,
phase, and coupling strength computation.

Physical Meaning:
    Computes the amplitude and phase of resonance modes at given frequencies
    from eigenvector analysis, and coupling strength between modes.

Mathematical Foundation:
    For each resonance frequency ω_n:
    - Amplitude: |A_n| from eigenvector analysis
    - Phase: arg(A_n) from eigenvector analysis
    - Coupling strength: inversely proportional to frequency separation

Example:
    >>> from bhlff.models.level_c.abcd_model.mode_analysis import ABCDModeAnalysis
    >>> analyzer = ABCDModeAnalysis(compute_transmission_matrix)
    >>> amplitude, phase = analyzer.compute_mode_amplitude_phase(frequency)
"""

import numpy as np
from typing import List, Tuple, Callable, Optional
import logging


class ABCDModeAnalysis:
    """
    Mode analysis for ABCD model.

    Physical Meaning:
        Provides methods for analyzing resonance modes, including amplitude,
        phase, and coupling strength computation.

    Mathematical Foundation:
        Implements mode analysis with eigenvector analysis and coupling
        strength computation.
    """

    def __init__(
        self,
        compute_transmission_matrix: Callable,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize mode analysis.

        Args:
            compute_transmission_matrix (Callable): Function to compute transmission matrix.
            logger (Optional[logging.Logger]): Logger instance.
        """
        self.compute_transmission_matrix = compute_transmission_matrix
        self.logger = logger or logging.getLogger(__name__)

    def compute_mode_amplitude_phase(self, frequency: float) -> Tuple[float, float]:
        """
        Compute mode amplitude and phase.

        Physical Meaning:
            Computes the amplitude and phase of the resonance mode
            at the given frequency from eigenvector analysis.

        Args:
            frequency (float): Frequency ω.

        Returns:
            Tuple[float, float]: (amplitude, phase) of the resonance mode.
        """
        T = self.compute_transmission_matrix(frequency)

        # Find eigenvalues and eigenvectors
        eigenvals, eigenvecs = np.linalg.eig(T)

        # Find eigenvalue closest to 1 (resonance condition)
        resonance_idx = np.argmin(np.abs(eigenvals - 1.0))
        eigenvec = eigenvecs[:, resonance_idx]

        amplitude = np.abs(eigenvec[0])
        phase = np.angle(eigenvec[0])

        return amplitude, phase

    def compute_coupling_strength(
        self, frequency: float, all_frequencies: List[float]
    ) -> float:
        """
        Compute coupling strength with other modes.

        Physical Meaning:
            Computes the coupling strength between the mode at the
            given frequency and other system modes.

        Args:
            frequency (float): Frequency ω.
            all_frequencies (List[float]): List of all resonance frequencies.

        Returns:
            float: Coupling strength.
        """
        if len(all_frequencies) <= 1:
            return 0.0

        # Find closest other frequency
        other_frequencies = [f for f in all_frequencies if f != frequency]
        if not other_frequencies:
            return 0.0

        closest_freq = min(other_frequencies, key=lambda f: abs(f - frequency))
        frequency_separation = abs(frequency - closest_freq)

        # Coupling strength inversely proportional to frequency separation
        coupling_strength = 1.0 / (1.0 + frequency_separation)

        return coupling_strength
