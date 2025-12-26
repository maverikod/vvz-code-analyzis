"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Feature calculators for ML prediction.

This module implements feature calculation methods for machine learning
prediction in 7D phase field beating analysis.

Physical Meaning:
    Implements specific feature calculation methods for extracting
    spectral, spatial, and temporal features from 7D phase field configurations.

Example:
    >>> calculator = FeatureCalculator()
    >>> entropy = calculator.calculate_spectral_entropy(envelope)
"""

import numpy as np
from typing import Dict, Any


class FeatureCalculator:
    """
    Feature calculator for ML prediction.

    Physical Meaning:
        Implements specific feature calculation methods for extracting
        spectral, spatial, and temporal features from 7D phase field configurations.

    Mathematical Foundation:
        Implements spectral analysis, spatial correlation, and temporal
        coherence calculations based on 7D phase field theory.
    """

    def __init__(self):
        """
        Initialize feature calculator.

        Physical Meaning:
            Sets up the feature calculation system for 7D phase field analysis.
        """
        # Initialize feature calculation parameters
        self.feature_cache = {}
        self.calculation_precision = 1e-12
        self.max_array_size = 1000000  # 1M elements threshold for memory management

    def calculate_spectral_entropy(self, envelope: np.ndarray) -> float:
        """
        Calculate spectral entropy from envelope.

        Physical Meaning:
            Computes spectral entropy as a measure of frequency
            distribution complexity in the 7D phase field.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Normalize to get probability distribution
        total_power = np.sum(power_spectrum)
        if total_power == 0:
            return 0.0

        probabilities = power_spectrum / total_power

        # Compute entropy
        entropy = -np.sum(probabilities * np.log(probabilities + 1e-10))
        return float(np.real(entropy))

    def calculate_frequency_spacing(self, envelope: np.ndarray, shape: tuple) -> float:
        """
        Calculate frequency spacing from envelope.

        Physical Meaning:
            Computes characteristic frequency spacing in the
            7D phase field configuration.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Find dominant frequencies
        max_indices = np.unravel_index(np.argmax(power_spectrum), power_spectrum.shape)

        # Calculate spacing based on grid
        spacing = 1.0 / np.min(shape)
        return float(np.real(spacing))

    def calculate_frequency_bandwidth(self, envelope: np.ndarray) -> float:
        """
        Calculate frequency bandwidth from envelope.

        Physical Meaning:
            Computes frequency bandwidth as a measure of
            spectral width in the 7D phase field.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Find bandwidth at half maximum
        max_power = np.max(power_spectrum)
        half_max = max_power / 2.0

        # Count frequencies above half maximum
        above_half_max = np.sum(power_spectrum > half_max)
        total_frequencies = power_spectrum.size

        bandwidth = above_half_max / total_frequencies
        return float(np.real(bandwidth))

    def calculate_autocorrelation(self, envelope: np.ndarray) -> float:
        """
        Calculate autocorrelation from envelope.

        Physical Meaning:
            Computes autocorrelation as a measure of temporal
            coherence in the 7D phase field.
        """
        # For large arrays, use sampling to avoid memory issues
        if envelope.size > 100000:  # 100K elements threshold
            # Sample the array to reduce computation time
            sample_size = min(10000, envelope.size // 10)
            flat_envelope = envelope.flatten()
            indices = np.random.choice(flat_envelope.size, sample_size, replace=False)
            sample_envelope = flat_envelope[indices]
        else:
            sample_envelope = envelope.flatten()

        # Compute autocorrelation on sampled data
        autocorr = np.correlate(sample_envelope, sample_envelope, mode="full")
        autocorr = autocorr[autocorr.size // 2 :]

        # Normalize
        if autocorr[0] != 0:
            autocorr = autocorr / autocorr[0]

        # Return maximum autocorrelation (excluding zero lag)
        if len(autocorr) > 1:
            return float(np.real(np.max(autocorr[1:])))
        else:
            return 0.0

    def calculate_frequency_coupling_strength(self, envelope: np.ndarray) -> float:
        """
        Calculate frequency coupling strength from envelope.

        Physical Meaning:
            Computes coupling strength between different frequency
            modes in the 7D phase field.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Find dominant modes
        sorted_indices = np.unravel_index(
            np.argsort(power_spectrum.ravel())[-2:], power_spectrum.shape
        )

        # Calculate coupling strength based on mode interaction
        mode1_power = power_spectrum[sorted_indices[0][0], sorted_indices[1][0]]
        mode2_power = power_spectrum[sorted_indices[0][1], sorted_indices[1][1]]

        # Ensure scalar values
        mode1_power = (
            np.real(mode1_power)
            if np.isscalar(mode1_power)
            else np.real(mode1_power[0])
        )
        mode2_power = (
            np.real(mode2_power)
            if np.isscalar(mode2_power)
            else np.real(mode2_power[0])
        )

        coupling_strength = np.sqrt(mode1_power * mode2_power) / np.sum(power_spectrum)

        # Ensure coupling_strength is a scalar
        if np.isscalar(coupling_strength):
            return float(np.real(coupling_strength))
        else:
            # Handle array case - take the first element and ensure it's scalar
            coupling_value = (
                coupling_strength[0]
                if hasattr(coupling_strength, "__getitem__")
                else coupling_strength
            )
            if np.isscalar(coupling_value):
                return float(np.real(coupling_value))
            else:
                # If still an array, take the first element recursively
                return float(np.real(coupling_value.flat[0]))

    def calculate_mode_interaction_energy(self, envelope: np.ndarray) -> float:
        """
        Calculate mode interaction energy from envelope.

        Physical Meaning:
            Computes interaction energy between different modes
            in the 7D phase field configuration.
        """
        # Compute gradient for interaction energy
        grad_x = np.gradient(envelope, axis=0)
        grad_y = np.gradient(envelope, axis=1)
        if envelope.ndim > 2:
            grad_z = np.gradient(envelope, axis=2)
            interaction_energy = np.sum(grad_x**2 + grad_y**2 + grad_z**2)
        else:
            interaction_energy = np.sum(grad_x**2 + grad_y**2)

        return float(np.real(interaction_energy))

    def calculate_coupling_symmetry(self, envelope: np.ndarray) -> float:
        """
        Calculate coupling symmetry from envelope.

        Physical Meaning:
            Computes symmetry measure of mode coupling
            in the 7D phase field.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Calculate symmetry measure
        center = tuple(s // 2 for s in power_spectrum.shape)
        symmetry = 0.0

        for i in range(power_spectrum.shape[0]):
            for j in range(power_spectrum.shape[1]):
                if power_spectrum.ndim > 2:
                    for k in range(power_spectrum.shape[2]):
                        # Check symmetry with respect to center
                        sym_i = 2 * center[0] - i
                        sym_j = 2 * center[1] - j
                        sym_k = 2 * center[2] - k

                        if (
                            0 <= sym_i < power_spectrum.shape[0]
                            and 0 <= sym_j < power_spectrum.shape[1]
                            and 0 <= sym_k < power_spectrum.shape[2]
                        ):
                            symmetry += abs(
                                power_spectrum[i, j, k]
                                - power_spectrum[sym_i, sym_j, sym_k]
                            )
                else:
                    sym_i = 2 * center[0] - i
                    sym_j = 2 * center[1] - j

                    if (
                        0 <= sym_i < power_spectrum.shape[0]
                        and 0 <= sym_j < power_spectrum.shape[1]
                    ):
                        symmetry += abs(
                            power_spectrum[i, j] - power_spectrum[sym_i, sym_j]
                        )

        # Normalize by total power
        total_power = np.sum(power_spectrum)
        if total_power > 0:
            symmetry = symmetry / total_power

        # Ensure symmetry is a scalar
        if np.isscalar(symmetry):
            return float(np.real(symmetry))
        else:
            # Handle array case - take the first element and ensure it's scalar
            symmetry_value = (
                symmetry[0] if hasattr(symmetry, "__getitem__") else symmetry
            )
            if np.isscalar(symmetry_value):
                return float(np.real(symmetry_value))
            else:
                # If still an array, take the first element recursively
                return float(np.real(symmetry_value.flat[0]))

    def calculate_nonlinear_strength(self, envelope: np.ndarray) -> float:
        """
        Calculate nonlinear strength from envelope.

        Physical Meaning:
            Computes nonlinear interaction strength in the
            7D phase field configuration.
        """
        # Compute nonlinear terms (cubic terms)
        nonlinear_term = envelope**3

        # Calculate nonlinear strength
        nonlinear_strength = np.sum(np.abs(nonlinear_term)) / np.sum(np.abs(envelope))

        return float(np.real(nonlinear_strength))

    def calculate_mode_mixing_degree(self, envelope: np.ndarray) -> float:
        """
        Calculate mode mixing degree from envelope.

        Physical Meaning:
            Computes degree of mode mixing in the 7D phase field
            configuration.
        """
        # Compute FFT
        fft_data = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_data) ** 2

        # Calculate mixing degree based on spectral distribution
        total_power = np.sum(power_spectrum)
        if total_power == 0:
            return 0.0

        # Find number of significant modes
        threshold = 0.1 * np.max(power_spectrum)
        significant_modes = np.sum(power_spectrum > threshold)
        total_modes = power_spectrum.size

        mixing_degree = significant_modes / total_modes
        return float(np.real(mixing_degree))

    def calculate_coupling_efficiency(self, envelope: np.ndarray) -> float:
        """
        Calculate coupling efficiency from envelope.

        Physical Meaning:
            Computes efficiency of mode coupling in the
            7D phase field configuration.
        """
        # Compute coupling efficiency based on energy transfer
        energy_density = envelope**2
        total_energy = np.sum(energy_density)

        if total_energy == 0:
            return 0.0

        # Calculate efficiency as energy concentration measure
        max_energy = np.max(energy_density)
        efficiency = max_energy / total_energy

        return float(np.real(efficiency))
