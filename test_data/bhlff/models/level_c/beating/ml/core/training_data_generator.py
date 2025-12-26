"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Training data generator for ML models.

This module implements training data generation for machine learning
models in 7D phase field beating analysis.

Physical Meaning:
    Generates comprehensive training datasets for ML models based on
    7D phase field theory and VBP envelope configurations.

Example:
    >>> generator = TrainingDataGenerator()
    >>> training_data = generator.generate_frequency_training_data(n_samples=1000)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from .bvp_7d_analytics import BVP7DAnalytics


class TrainingDataGenerator:
    """
    Training data generator for ML models.

    Physical Meaning:
        Generates comprehensive training datasets for ML models based on
        7D phase field theory and VBP envelope configurations.

    Mathematical Foundation:
        Uses 7D phase field theory to generate synthetic training data
        with known frequency and coupling parameters.
    """

    def __init__(self):
        """
        Initialize training data generator.

        Physical Meaning:
            Sets up the training data generation system for 7D phase field analysis.
        """
        self.bvp_analytics = BVP7DAnalytics()
        self.logger = logging.getLogger(__name__)

        # 7D phase field parameters for data generation
        self.phase_field_params = {
            "spectral_entropy_range": (0.1, 2.0),
            "frequency_spacing_range": (0.05, 1.0),
            "frequency_bandwidth_range": (0.1, 2.0),
            "coupling_strength_range": (0.1, 1.0),
            "interaction_energy_range": (0.1, 2.0),
            "coupling_symmetry_range": (0.1, 1.0),
            "nonlinear_strength_range": (0.1, 1.0),
            "mixing_degree_range": (0.1, 1.0),
            "coupling_efficiency_range": (0.1, 1.0),
            "phase_coherence_range": (0.1, 1.0),
            "topological_charge_range": (-2.0, 2.0),
        }

    def generate_frequency_training_data(
        self, n_samples: int = 1000
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate training data for frequency prediction.

        Physical Meaning:
            Generates training data for frequency prediction using
            7D phase field theory and VBP envelope configurations.

        Mathematical Foundation:
            Creates synthetic 7D phase field configurations with known
            frequency parameters for ML model training.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Tuple[np.ndarray, np.ndarray]: (features, targets) for training.
        """
        self.logger.info(f"Generating {n_samples} frequency training samples")

        features_list = []
        targets_list = []

        for i in range(n_samples):
            # Generate random 7D phase field parameters
            phase_params = self._generate_random_phase_params()

            # Generate synthetic envelope field
            envelope = self._generate_synthetic_envelope(phase_params)

            # Extract features from envelope
            features = self._extract_training_features(envelope, phase_params)

            # Compute target frequencies using 7D BVP theory
            target_frequencies = self._compute_target_frequencies(phase_params)

            features_list.append(features)
            targets_list.append(target_frequencies)

        return np.array(features_list), np.array(targets_list)

    def generate_coupling_training_data(
        self, n_samples: int = 1000
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate training data for coupling prediction.

        Physical Meaning:
            Generates training data for coupling prediction using
            7D phase field theory and VBP envelope interactions.

        Mathematical Foundation:
            Creates synthetic 7D phase field configurations with known
            coupling parameters for ML model training.

        Args:
            n_samples (int): Number of training samples to generate.

        Returns:
            Tuple[np.ndarray, np.ndarray]: (features, targets) for training.
        """
        self.logger.info(f"Generating {n_samples} coupling training samples")

        features_list = []
        targets_list = []

        for i in range(n_samples):
            # Generate random 7D phase field parameters
            phase_params = self._generate_random_phase_params()

            # Generate synthetic envelope field
            envelope = self._generate_synthetic_envelope(phase_params)

            # Extract features from envelope
            features = self._extract_training_features(envelope, phase_params)

            # Compute target coupling parameters using 7D BVP theory
            target_coupling = self._compute_target_coupling(phase_params)

            features_list.append(features)
            targets_list.append(target_coupling)

        return np.array(features_list), np.array(targets_list)

    def _generate_random_phase_params(self) -> Dict[str, float]:
        """Generate random 7D phase field parameters."""
        params = {}
        for param_name, (min_val, max_val) in self.phase_field_params.items():
            params[param_name] = np.random.uniform(min_val, max_val)
        return params

    def _generate_synthetic_envelope(
        self, phase_params: Dict[str, float]
    ) -> np.ndarray:
        """
        Generate synthetic envelope field based on 7D phase field parameters.

        Physical Meaning:
            Generates synthetic envelope field configuration based on
            7D phase field theory and VBP envelope dynamics.

        Args:
            phase_params (Dict[str, float]): 7D phase field parameters.

        Returns:
            np.ndarray: Synthetic envelope field.
        """
        # Generate 3D spatial grid
        x = np.linspace(-5, 5, 64)
        y = np.linspace(-5, 5, 64)
        z = np.linspace(-5, 5, 64)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Compute 7D phase field envelope
        r = np.sqrt(X**2 + Y**2 + Z**2)

        # Base envelope from 7D phase field theory using step function
        envelope = self._step_resonator_envelope(
            r, phase_params["spectral_entropy_range"]
        )

        # Add phase coherence effects
        phase_coherence = phase_params["phase_coherence_range"]
        envelope *= 1 + phase_coherence * np.cos(r)

        # Add topological charge effects
        topological_charge = phase_params["topological_charge_range"]
        if abs(topological_charge) > 0.1:
            envelope *= 1 + topological_charge * np.sin(r) / r

        # Add coupling effects
        coupling_strength = phase_params["coupling_strength_range"]
        envelope *= 1 + coupling_strength * np.sin(2 * r)

        return envelope

    def _extract_training_features(
        self, envelope: np.ndarray, phase_params: Dict[str, float]
    ) -> np.ndarray:
        """Extract training features from envelope and parameters."""
        # Basic spectral features
        spectral_entropy = phase_params["spectral_entropy_range"]
        frequency_spacing = phase_params["frequency_spacing_range"]
        frequency_bandwidth = phase_params["frequency_bandwidth_range"]

        # Coupling features
        coupling_strength = phase_params["coupling_strength_range"]
        interaction_energy = phase_params["interaction_energy_range"]
        coupling_symmetry = phase_params["coupling_symmetry_range"]
        nonlinear_strength = phase_params["nonlinear_strength_range"]
        mixing_degree = phase_params["mixing_degree_range"]
        coupling_efficiency = phase_params["coupling_efficiency_range"]

        # 7D phase field features
        phase_coherence = phase_params["phase_coherence_range"]
        topological_charge = phase_params["topological_charge_range"]

        # Compute energy density and phase velocity
        energy_density = np.mean(envelope**2)
        phase_velocity = np.std(envelope)

        # Compute autocorrelation
        autocorrelation = np.corrcoef(
            envelope.flatten(), np.roll(envelope.flatten(), 1)
        )[0, 1]

        return np.array(
            [
                spectral_entropy,
                frequency_spacing,
                frequency_bandwidth,
                autocorrelation,
                coupling_strength,
                interaction_energy,
                coupling_symmetry,
                nonlinear_strength,
                mixing_degree,
                coupling_efficiency,
                phase_coherence,
                topological_charge,
                energy_density,
                phase_velocity,
            ]
        )

    def _compute_target_frequencies(self, phase_params: Dict[str, float]) -> np.ndarray:
        """Compute target frequencies using 7D BVP theory."""
        # Extract parameters
        spectral_entropy = phase_params["spectral_entropy_range"]
        frequency_spacing = phase_params["frequency_spacing_range"]
        frequency_bandwidth = phase_params["frequency_bandwidth_range"]
        phase_coherence = phase_params["phase_coherence_range"]
        topological_charge = phase_params["topological_charge_range"]

        # Compute target frequencies using 7D BVP theory
        base_frequency = self.bvp_analytics._compute_base_frequency_7d(
            spectral_entropy, phase_coherence
        )
        spacing_factor = self.bvp_analytics._compute_spacing_factor_7d(
            frequency_spacing, topological_charge
        )
        bandwidth_factor = self.bvp_analytics._compute_bandwidth_factor_7d(
            frequency_bandwidth, phase_coherence
        )

        return np.array(
            [
                base_frequency * spacing_factor,
                base_frequency * bandwidth_factor,
                base_frequency * (spacing_factor + bandwidth_factor) / 2.0,
            ]
        )

    def _compute_target_coupling(self, phase_params: Dict[str, float]) -> np.ndarray:
        """Compute target coupling parameters using 7D BVP theory."""
        # Extract parameters
        coupling_strength = phase_params["coupling_strength_range"]
        interaction_energy = phase_params["interaction_energy_range"]
        coupling_symmetry = phase_params["coupling_symmetry_range"]
        nonlinear_strength = phase_params["nonlinear_strength_range"]
        mixing_degree = phase_params["mixing_degree_range"]
        coupling_efficiency = phase_params["coupling_efficiency_range"]
        phase_coherence = phase_params["phase_coherence_range"]
        topological_charge = phase_params["topological_charge_range"]

        # Compute target coupling using 7D BVP theory
        target_coupling = self.bvp_analytics.compute_7d_coupling_prediction(
            np.array([0.0]),  # Dummy phase features
            {
                "coupling_strength": coupling_strength,
                "interaction_energy": interaction_energy,
                "coupling_symmetry": coupling_symmetry,
                "nonlinear_strength": nonlinear_strength,
                "mixing_degree": mixing_degree,
                "coupling_efficiency": coupling_efficiency,
                "phase_coherence": phase_coherence,
                "topological_charge": topological_charge,
            },
        )

        return np.array(
            [
                target_coupling["coupling_strength"],
                target_coupling["interaction_energy"],
                target_coupling["coupling_symmetry"],
                target_coupling["nonlinear_strength"],
                target_coupling["mixing_degree"],
                target_coupling["coupling_efficiency"],
            ]
        )

    def _step_resonator_envelope(
        self, r: np.ndarray, spectral_entropy_range: float
    ) -> np.ndarray:
        """
        Step resonator envelope according to 7D BVP theory.

        Physical Meaning:
            Implements step function envelope instead of exponential decay
            according to 7D BVP theory principles where field boundaries
            are determined by step functions rather than smooth transitions.

        Mathematical Foundation:
            Envelope = Θ(r_cutoff - r) where Θ is the Heaviside step function
            and r_cutoff is the cutoff radius for the field.

        Args:
            r (np.ndarray): Radial distance from center.
            spectral_entropy_range (float): Cutoff radius for the field.

        Returns:
            np.ndarray: Step function envelope according to 7D BVP theory.
        """
        # Step function envelope according to 7D BVP theory
        cutoff_radius = spectral_entropy_range
        transmission_coeff = 1.0

        # Apply step function boundary condition
        envelope = transmission_coeff * np.where(r < cutoff_radius, 1.0, 0.0)

        return envelope
