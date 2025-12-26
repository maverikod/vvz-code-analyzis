"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Feature extraction functionality.

This module implements feature extraction for ML prediction including
spectral, spatial, and temporal features from 7D phase field data.

Physical Meaning:
    Extracts comprehensive features from 7D phase field configurations
    for machine learning-based prediction of beating frequencies and mode coupling.

Example:
    >>> extractor = FeatureExtractor()
    >>> features = extractor.extract_frequency_features(envelope)
"""

import numpy as np
from typing import Dict, Any
import logging
from scipy import signal
from scipy.stats import entropy


class FeatureExtractor:
    """
    Feature extractor for ML prediction.

    Physical Meaning:
        Extracts comprehensive features from 7D phase field configurations
        for machine learning-based prediction of beating frequencies and mode coupling.

    Mathematical Foundation:
        Computes spectral, spatial, and temporal features from 7D phase field data
        for ML-based prediction analysis.
    """

    def __init__(self):
        """Initialize feature extractor."""
        self.logger = logging.getLogger(__name__)

    def extract_frequency_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract frequency prediction features from 7D phase field data.

        Physical Meaning:
            Extracts features relevant for frequency prediction from
            7D phase field envelope data using spectral analysis.

        Mathematical Foundation:
            Computes spectral entropy, frequency spacing, bandwidth,
            and other frequency-related features from 7D phase field data.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Frequency prediction features.
        """
        try:
            # Compute spectral features
            spectral_entropy = self._compute_spectral_entropy(envelope)
            frequency_spacing = self._compute_frequency_spacing(envelope)
            frequency_bandwidth = self._compute_frequency_bandwidth(envelope)
            autocorrelation = self._compute_autocorrelation(envelope)

            # Compute 7D phase field features
            phase_coherence = self._compute_phase_coherence(envelope)
            topological_charge = self._compute_topological_charge(envelope)
            energy_density = self._compute_energy_density(envelope)
            phase_velocity = self._compute_phase_velocity(envelope)

            return {
                "spectral_entropy": spectral_entropy,
                "frequency_spacing": frequency_spacing,
                "frequency_bandwidth": frequency_bandwidth,
                "autocorrelation": autocorrelation,
                "phase_coherence": phase_coherence,
                "topological_charge": topological_charge,
                "energy_density": energy_density,
                "phase_velocity": phase_velocity,
            }

        except Exception as e:
            self.logger.error(f"Frequency feature extraction failed: {e}")
            return {}

    def extract_coupling_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract coupling prediction features from 7D phase field data.

        Physical Meaning:
            Extracts features relevant for mode coupling prediction from
            7D phase field envelope data using interaction analysis.

        Mathematical Foundation:
            Computes coupling strength, interaction energy, symmetry,
            and other coupling-related features from 7D phase field data.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Coupling prediction features.
        """
        try:
            # Compute coupling features
            coupling_strength = self._compute_coupling_strength(envelope)
            interaction_energy = self._compute_interaction_energy(envelope)
            coupling_symmetry = self._compute_coupling_symmetry(envelope)
            nonlinear_strength = self._compute_nonlinear_strength(envelope)
            mixing_degree = self._compute_mixing_degree(envelope)
            coupling_efficiency = self._compute_coupling_efficiency(envelope)

            # Compute 7D phase field features
            phase_coherence = self._compute_phase_coherence(envelope)
            topological_charge = self._compute_topological_charge(envelope)
            energy_density = self._compute_energy_density(envelope)
            phase_velocity = self._compute_phase_velocity(envelope)

            return {
                "coupling_strength": coupling_strength,
                "interaction_energy": interaction_energy,
                "coupling_symmetry": coupling_symmetry,
                "nonlinear_strength": nonlinear_strength,
                "mixing_degree": mixing_degree,
                "coupling_efficiency": coupling_efficiency,
                "phase_coherence": phase_coherence,
                "topological_charge": topological_charge,
                "energy_density": energy_density,
                "phase_velocity": phase_velocity,
            }

        except Exception as e:
            self.logger.error(f"Coupling feature extraction failed: {e}")
            return {}

    def extract_7d_phase_features(self, features: Dict[str, Any]) -> np.ndarray:
        """
        Extract 7D phase field features for ML input.

        Physical Meaning:
            Extracts 7D phase field specific features for machine learning
            input from comprehensive feature dictionary.

        Args:
            features (Dict[str, Any]): Comprehensive feature dictionary.

        Returns:
            np.ndarray: 7D phase field features array.
        """
        try:
            # Extract 7D phase field features in order
            phase_features = [
                features.get("spectral_entropy", 0.0),
                features.get("frequency_spacing", 0.0),
                features.get("frequency_bandwidth", 0.0),
                features.get("autocorrelation", 0.0),
                features.get("coupling_strength", 0.0),
                features.get("interaction_energy", 0.0),
                features.get("coupling_symmetry", 0.0),
                features.get("nonlinear_strength", 0.0),
                features.get("mixing_degree", 0.0),
                features.get("coupling_efficiency", 0.0),
                features.get("phase_coherence", 0.0),
                features.get("topological_charge", 0.0),
                features.get("energy_density", 0.0),
                features.get("phase_velocity", 0.0),
            ]

            return np.array(phase_features)

        except Exception as e:
            self.logger.error(f"7D phase feature extraction failed: {e}")
            return np.zeros(14)

    def _compute_spectral_entropy(self, envelope: np.ndarray) -> float:
        """Compute spectral entropy from envelope data."""
        try:
            # Compute power spectral density
            freqs, psd = signal.welch(envelope.flatten())

            # Normalize PSD
            psd_norm = psd / np.sum(psd)

            # Compute spectral entropy
            spectral_entropy = entropy(psd_norm)

            return float(spectral_entropy)

        except Exception as e:
            self.logger.error(f"Spectral entropy computation failed: {e}")
            return 0.0

    def _compute_frequency_spacing(self, envelope: np.ndarray) -> float:
        """Compute frequency spacing from envelope data."""
        try:
            # Compute power spectral density
            freqs, psd = signal.welch(envelope.flatten())

            # Find peaks in PSD
            peaks, _ = signal.find_peaks(psd, height=np.max(psd) * 0.1)

            if len(peaks) > 1:
                # Compute average spacing between peaks
                peak_freqs = freqs[peaks]
                spacing = np.mean(np.diff(peak_freqs))
                return float(spacing)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Frequency spacing computation failed: {e}")
            return 0.0

    def _compute_frequency_bandwidth(self, envelope: np.ndarray) -> float:
        """Compute frequency bandwidth from envelope data."""
        try:
            # Compute power spectral density
            freqs, psd = signal.welch(envelope.flatten())

            # Find bandwidth at half maximum
            max_psd = np.max(psd)
            half_max = max_psd / 2

            # Find indices where PSD is above half maximum
            above_half_max = psd >= half_max

            if np.any(above_half_max):
                # Compute bandwidth
                bandwidth = freqs[above_half_max][-1] - freqs[above_half_max][0]
                return float(bandwidth)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Frequency bandwidth computation failed: {e}")
            return 0.0

    def _compute_autocorrelation(self, envelope: np.ndarray) -> float:
        """Compute autocorrelation from envelope data."""
        try:
            # Compute autocorrelation
            autocorr = np.correlate(envelope.flatten(), envelope.flatten(), mode="full")
            autocorr = autocorr[autocorr.size // 2 :]

            # Normalize
            autocorr = autocorr / autocorr[0]

            # Find first zero crossing
            zero_crossings = np.where(np.diff(np.sign(autocorr)))[0]

            if len(zero_crossings) > 0:
                return float(zero_crossings[0])
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Autocorrelation computation failed: {e}")
            return 0.0

    def _compute_coupling_strength(self, envelope: np.ndarray) -> float:
        """Compute coupling strength from envelope data."""
        try:
            # Compute coupling strength as variance of envelope
            coupling_strength = np.var(envelope)
            return float(coupling_strength)

        except Exception as e:
            self.logger.error(f"Coupling strength computation failed: {e}")
            return 0.0

    def _compute_interaction_energy(self, envelope: np.ndarray) -> float:
        """Compute interaction energy from envelope data."""
        try:
            # Compute interaction energy as mean squared envelope
            interaction_energy = np.mean(envelope**2)
            return float(interaction_energy)

        except Exception as e:
            self.logger.error(f"Interaction energy computation failed: {e}")
            return 0.0

    def _compute_coupling_symmetry(self, envelope: np.ndarray) -> float:
        """Compute coupling symmetry from envelope data."""
        try:
            # Compute symmetry as correlation with flipped version
            envelope_flat = envelope.flatten()
            flipped = np.flip(envelope_flat)

            # Compute correlation
            if len(envelope_flat) > 1:
                correlation = np.corrcoef(envelope_flat, flipped)[0, 1]
                return float(correlation) if not np.isnan(correlation) else 0.0
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Coupling symmetry computation failed: {e}")
            return 0.0

    def _compute_nonlinear_strength(self, envelope: np.ndarray) -> float:
        """Compute nonlinear strength from envelope data."""
        try:
            # Compute nonlinear strength as skewness
            envelope_flat = envelope.flatten()
            mean_val = np.mean(envelope_flat)
            std_val = np.std(envelope_flat)

            if std_val > 0:
                skewness = np.mean(((envelope_flat - mean_val) / std_val) ** 3)
                return float(skewness)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Nonlinear strength computation failed: {e}")
            return 0.0

    def _compute_mixing_degree(self, envelope: np.ndarray) -> float:
        """Compute mixing degree from envelope data."""
        try:
            # Compute mixing degree as kurtosis
            envelope_flat = envelope.flatten()
            mean_val = np.mean(envelope_flat)
            std_val = np.std(envelope_flat)

            if std_val > 0:
                kurtosis = np.mean(((envelope_flat - mean_val) / std_val) ** 4) - 3
                return float(kurtosis)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Mixing degree computation failed: {e}")
            return 0.0

    def _compute_coupling_efficiency(self, envelope: np.ndarray) -> float:
        """Compute coupling efficiency from envelope data."""
        try:
            # Compute coupling efficiency as ratio of energy to variance
            energy = np.sum(envelope**2)
            variance = np.var(envelope)

            if variance > 0:
                efficiency = energy / variance
                return float(efficiency)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Coupling efficiency computation failed: {e}")
            return 0.0

    def _compute_phase_coherence(self, envelope: np.ndarray) -> float:
        """Compute phase coherence from envelope data."""
        try:
            # Compute phase coherence as magnitude of mean complex phase
            complex_phase = np.exp(1j * np.angle(envelope))
            phase_coherence = np.abs(np.mean(complex_phase))
            return float(phase_coherence)

        except Exception as e:
            self.logger.error(f"Phase coherence computation failed: {e}")
            return 0.0

    def _compute_topological_charge(self, envelope: np.ndarray) -> float:
        """Compute topological charge from envelope data."""
        try:
            # Compute topological charge as winding number
            envelope_flat = envelope.flatten()
            if len(envelope_flat) > 1:
                phase_gradient = np.gradient(np.angle(envelope_flat))
                topological_charge = np.sum(phase_gradient) / (2 * np.pi)
                return float(topological_charge)
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Topological charge computation failed: {e}")
            return 0.0

    def _compute_energy_density(self, envelope: np.ndarray) -> float:
        """Compute energy density from envelope data."""
        try:
            # Compute energy density as mean squared envelope
            energy_density = np.mean(envelope**2)
            return float(energy_density)

        except Exception as e:
            self.logger.error(f"Energy density computation failed: {e}")
            return 0.0

    def _compute_phase_velocity(self, envelope: np.ndarray) -> float:
        """Compute phase velocity from envelope data."""
        try:
            # Compute phase velocity as standard deviation of phase
            phase_velocity = np.std(np.angle(envelope))
            return float(phase_velocity)

        except Exception as e:
            self.logger.error(f"Phase velocity computation failed: {e}")
            return 0.0
