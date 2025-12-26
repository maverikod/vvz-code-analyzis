"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Machine learning prediction features module.

This module implements feature extraction functionality for ML prediction
in Level C of 7D phase field theory.

Physical Meaning:
    Provides feature extraction functions for ML prediction
    of beating frequencies and mode coupling.

Example:
    >>> feature_extractor = BeatingMLPredictionFeatures(bvp_core)
    >>> features = feature_extractor.extract_frequency_features(envelope)
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore


class BeatingMLPredictionFeatures:
    """
    Machine learning prediction features for beating analysis.

    Physical Meaning:
        Provides feature extraction functions for ML prediction
        of beating frequencies and mode coupling.

    Mathematical Foundation:
        Implements feature extraction for ML prediction:
        - Spectral features for frequency prediction
        - Coupling features for mode coupling analysis
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize feature extractor.

        Physical Meaning:
            Sets up the feature extraction system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def _calculate_spectral_entropy(self, spectrum: np.ndarray) -> float:
        """
        Calculate spectral entropy.

        Physical Meaning:
            Calculates spectral entropy of field spectrum
            for frequency prediction.

        Args:
            spectrum (np.ndarray): Field spectrum.

        Returns:
            float: Spectral entropy.
        """
        # Calculate histogram
        histogram, _ = np.histogram(spectrum, bins=50)
        histogram = histogram / np.sum(histogram)  # Normalize

        # Calculate entropy
        entropy = -np.sum(histogram * np.log(histogram + 1e-10))

        return entropy

    def _calculate_frequency_spacing(self, indices: np.ndarray, shape: tuple) -> float:
        """
        Calculate frequency spacing.

        Physical Meaning:
            Calculates frequency spacing in field
            for frequency prediction.

        Args:
            indices (np.ndarray): Frequency indices.
            shape (tuple): Field shape.

        Returns:
            float: Frequency spacing.
        """
        # Calculate frequency spacing
        if len(indices) > 1:
            spacing = np.mean(np.diff(np.sort(indices)))
        else:
            spacing = 1.0

        return spacing

    def _calculate_frequency_bandwidth(self, spectrum: np.ndarray) -> float:
        """
        Calculate frequency bandwidth.

        Physical Meaning:
            Calculates frequency bandwidth of field spectrum
            for frequency prediction.

        Args:
            spectrum (np.ndarray): Field spectrum.

        Returns:
            float: Frequency bandwidth.
        """
        # Calculate bandwidth
        bandwidth = np.max(spectrum) - np.min(spectrum)

        return bandwidth

    def _calculate_autocorrelation(self, envelope: np.ndarray) -> float:
        """
        Calculate autocorrelation.

        Physical Meaning:
            Calculates autocorrelation of field envelope
            for frequency prediction.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            float: Autocorrelation.
        """
        # Calculate autocorrelation
        autocorrelation = np.corrcoef(envelope.flatten(), envelope.flatten())[0, 1]

        return autocorrelation

    def _calculate_laplacian(self, envelope: np.ndarray) -> np.ndarray:
        """
        Calculate Laplacian.

        Physical Meaning:
            Calculates Laplacian of field envelope
            for spatial analysis.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            np.ndarray: Laplacian field.
        """
        # Calculate Laplacian
        laplacian = np.zeros_like(envelope)

        # Calculate second derivatives
        for i in range(1, envelope.shape[0] - 1):
            for j in range(1, envelope.shape[1] - 1):
                for k in range(1, envelope.shape[2] - 1):
                    laplacian[i, j, k] = (
                        envelope[i + 1, j, k]
                        - 2 * envelope[i, j, k]
                        + envelope[i - 1, j, k]
                        + envelope[i, j + 1, k]
                        - 2 * envelope[i, j, k]
                        + envelope[i, j - 1, k]
                        + envelope[i, j, k + 1]
                        - 2 * envelope[i, j, k]
                        + envelope[i, j, k - 1]
                    )

        return laplacian

    def _calculate_spatial_correlation(self, envelope: np.ndarray) -> float:
        """
        Calculate spatial correlation.

        Physical Meaning:
            Calculates spatial correlation of field envelope
            for coupling analysis.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            float: Spatial correlation.
        """
        # Calculate spatial correlation
        # Simplified calculation
        correlation = np.corrcoef(
            envelope[0, :, :].flatten(), envelope[-1, :, :].flatten()
        )[0, 1]

        return correlation

    def _calculate_frequency_coupling_strength(self, spectrum: np.ndarray) -> float:
        """
        Calculate frequency coupling strength.

        Physical Meaning:
            Calculates frequency coupling strength
            for mode coupling analysis.

        Args:
            spectrum (np.ndarray): Field spectrum.

        Returns:
            float: Frequency coupling strength.
        """
        # Calculate coupling strength
        coupling_strength = np.std(spectrum) / np.mean(spectrum)

        return coupling_strength

    def _calculate_mode_interaction_energy(self, spectrum: np.ndarray) -> float:
        """
        Calculate mode interaction energy.

        Physical Meaning:
            Calculates mode interaction energy
            for coupling analysis.

        Args:
            spectrum (np.ndarray): Field spectrum.

        Returns:
            float: Mode interaction energy.
        """
        # Calculate interaction energy
        interaction_energy = np.sum(spectrum**2)

        return interaction_energy

    def _calculate_coupling_symmetry(self, spectrum: np.ndarray) -> float:
        """
        Calculate coupling symmetry.

        Physical Meaning:
            Calculates coupling symmetry
            for mode coupling analysis.

        Args:
            spectrum (np.ndarray): Field spectrum.

        Returns:
            float: Coupling symmetry.
        """
        # Calculate symmetry
        center = len(spectrum) // 2
        left_half = spectrum[:center]
        right_half = spectrum[center:]

        symmetry = np.corrcoef(left_half, right_half)[0, 1]

        return symmetry

    def _calculate_nonlinear_strength(self, envelope: np.ndarray) -> float:
        """
        Calculate nonlinear strength.

        Physical Meaning:
            Calculates nonlinear strength of field
            for coupling analysis.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            float: Nonlinear strength.
        """
        # Calculate nonlinear strength
        nonlinear_strength = np.mean(np.abs(envelope) ** 3)

        return nonlinear_strength

    def _calculate_mode_mixing_degree(self, envelope: np.ndarray) -> float:
        """
        Calculate mode mixing degree.

        Physical Meaning:
            Calculates mode mixing degree
            for coupling analysis.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            float: Mode mixing degree.
        """
        # Calculate mixing degree
        mixing_degree = np.std(envelope) / np.mean(envelope)

        return mixing_degree

    def _calculate_coupling_efficiency(self, envelope: np.ndarray) -> float:
        """
        Calculate coupling efficiency.

        Physical Meaning:
            Calculates coupling efficiency
            for mode coupling analysis.

        Args:
            envelope (np.ndarray): Field envelope.

        Returns:
            float: Coupling efficiency.
        """
        # Calculate coupling efficiency
        efficiency = np.mean(envelope) / np.max(envelope)

        return efficiency
