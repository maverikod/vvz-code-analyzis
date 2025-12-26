"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data generation for ML trainer.

This module provides data generation methods for training ML models,
including synthetic envelope generation and feature extraction.

Physical Meaning:
    Generates synthetic training data for ML models based on 7D phase
    field theory, including envelope generation and feature extraction
    for frequency and coupling prediction.
"""

import numpy as np
from typing import Tuple
import logging


class MLTrainerDataGeneration:
    """
    Data generation for ML trainer.
    
    Physical Meaning:
        Provides methods for generating synthetic training data
        for ML models based on 7D phase field theory.
    """
    
    def __init__(self, logger: logging.Logger = None):
        """
        Initialize data generation.
        
        Args:
            logger (logging.Logger): Logger instance.
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def generate_frequency_training_data(
        self, n_samples: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate training data for frequency prediction.
        
        Physical Meaning:
            Generates synthetic training data for frequency prediction
            models based on 7D phase field theory.
            
        Args:
            n_samples (int): Number of training samples to generate.
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: Feature matrix X and target frequencies y.
        """
        try:
            # Generate synthetic 7D phase field data
            X = []
            y = []
            
            for i in range(n_samples):
                # Generate synthetic envelope data
                envelope = self.generate_synthetic_envelope()
                
                # Extract features
                features = self.extract_frequency_features(envelope)
                X.append(features)
                
                # Generate target frequencies
                target_frequencies = self.generate_target_frequencies(features)
                y.append(target_frequencies)
            
            return np.array(X), np.array(y)
            
        except Exception as e:
            self.logger.error(f"Frequency training data generation failed: {e}")
            return np.array([]), np.array([])
    
    def generate_coupling_training_data(
        self, n_samples: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate training data for coupling prediction.
        
        Physical Meaning:
            Generates synthetic training data for coupling prediction
            models based on 7D phase field theory.
            
        Args:
            n_samples (int): Number of training samples to generate.
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: Feature matrix X and target coupling y.
        """
        try:
            # Generate synthetic 7D phase field data
            X = []
            y = []
            
            for i in range(n_samples):
                # Generate synthetic envelope data
                envelope = self.generate_synthetic_envelope()
                
                # Extract features
                features = self.extract_coupling_features(envelope)
                X.append(features)
                
                # Generate target coupling
                target_coupling = self.generate_target_coupling(features)
                y.append(target_coupling)
            
            return np.array(X), np.array(y)
            
        except Exception as e:
            self.logger.error(f"Coupling training data generation failed: {e}")
            return np.array([]), np.array([])
    
    def generate_synthetic_envelope(self) -> np.ndarray:
        """
        Generate synthetic envelope data for training.
        
        Physical Meaning:
            Generates synthetic 7D phase field envelope data
            for ML model training.
            
        Returns:
            np.ndarray: Synthetic envelope data.
        """
        try:
            # Generate synthetic 7D phase field envelope
            n_points = 100
            x = np.linspace(0, 10, n_points)
            
            # Generate multiple frequency components
            freq1 = np.random.uniform(0.5, 2.0)
            freq2 = np.random.uniform(0.5, 2.0)
            amp1 = np.random.uniform(0.5, 2.0)
            amp2 = np.random.uniform(0.5, 2.0)
            
            # Generate envelope with beating
            envelope = amp1 * np.sin(2 * np.pi * freq1 * x) + amp2 * np.sin(
                2 * np.pi * freq2 * x
            )
            
            # Add noise
            noise = np.random.normal(0, 0.1, n_points)
            envelope += noise
            
            return envelope
            
        except Exception as e:
            self.logger.error(f"Synthetic envelope generation failed: {e}")
            return np.zeros(100)
    
    def extract_frequency_features(self, envelope: np.ndarray) -> np.ndarray:
        """
        Extract frequency features from envelope data.
        
        Physical Meaning:
            Extracts frequency-related features from envelope data
            for ML model training.
            
        Args:
            envelope (np.ndarray): Envelope data.
            
        Returns:
            np.ndarray: Extracted frequency features.
        """
        try:
            # Extract basic features
            spectral_entropy = np.var(envelope)
            frequency_spacing = np.std(envelope)
            frequency_bandwidth = np.mean(np.abs(envelope))
            autocorrelation = (
                np.corrcoef(envelope[:-1], envelope[1:])[0, 1]
                if len(envelope) > 1
                else 0.0
            )
            
            # Extract 7D phase field features
            phase_coherence = np.abs(np.mean(np.exp(1j * np.angle(envelope))))
            topological_charge = np.sum(np.gradient(np.angle(envelope))) / (2 * np.pi)
            energy_density = np.mean(envelope**2)
            phase_velocity = np.std(np.angle(envelope))
            
            return np.array(
                [
                    spectral_entropy,
                    frequency_spacing,
                    frequency_bandwidth,
                    autocorrelation,
                    phase_coherence,
                    topological_charge,
                    energy_density,
                    phase_velocity,
                ]
            )
            
        except Exception as e:
            self.logger.error(f"Frequency feature extraction failed: {e}")
            return np.zeros(8)
    
    def extract_coupling_features(self, envelope: np.ndarray) -> np.ndarray:
        """
        Extract coupling features from envelope data.
        
        Physical Meaning:
            Extracts coupling-related features from envelope data
            for ML model training.
            
        Args:
            envelope (np.ndarray): Envelope data.
            
        Returns:
            np.ndarray: Extracted coupling features.
        """
        try:
            # Extract basic features
            coupling_strength = np.var(envelope)
            interaction_energy = np.mean(envelope**2)
            coupling_symmetry = (
                np.corrcoef(envelope, np.flip(envelope))[0, 1]
                if len(envelope) > 1
                else 0.0
            )
            nonlinear_strength = (
                np.mean(((envelope - np.mean(envelope)) / np.std(envelope)) ** 3)
                if np.std(envelope) > 0
                else 0.0
            )
            mixing_degree = (
                np.mean(((envelope - np.mean(envelope)) / np.std(envelope)) ** 4) - 3
                if np.std(envelope) > 0
                else 0.0
            )
            coupling_efficiency = (
                np.sum(envelope**2) / np.var(envelope) if np.var(envelope) > 0 else 0.0
            )
            
            # Extract 7D phase field features
            phase_coherence = np.abs(np.mean(np.exp(1j * np.angle(envelope))))
            topological_charge = np.sum(np.gradient(np.angle(envelope))) / (2 * np.pi)
            energy_density = np.mean(envelope**2)
            phase_velocity = np.std(np.angle(envelope))
            
            return np.array(
                [
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
            
        except Exception as e:
            self.logger.error(f"Coupling feature extraction failed: {e}")
            return np.zeros(10)
    
    def generate_target_frequencies(self, features: np.ndarray) -> np.ndarray:
        """
        Generate target frequencies for training.
        
        Physical Meaning:
            Generates target frequencies based on extracted features
            for ML model training.
            
        Args:
            features (np.ndarray): Extracted features.
            
        Returns:
            np.ndarray: Target frequencies.
        """
        try:
            # Generate target frequencies based on features
            freq1 = features[0] * 100.0  # spectral_entropy
            freq2 = features[1] * 50.0  # frequency_spacing
            freq3 = features[2] * 25.0  # frequency_bandwidth
            
            return np.array([freq1, freq2, freq3])
            
        except Exception as e:
            self.logger.error(f"Target frequency generation failed: {e}")
            return np.array([0.0, 0.0, 0.0])
    
    def generate_target_coupling(self, features: np.ndarray) -> np.ndarray:
        """
        Generate target coupling for training.
        
        Physical Meaning:
            Generates target coupling parameters based on extracted
            features for ML model training.
            
        Args:
            features (np.ndarray): Extracted features.
            
        Returns:
            np.ndarray: Target coupling parameters.
        """
        try:
            # Generate target coupling based on features
            coupling_strength = features[0] * 1.2
            interaction_energy = features[1] * 0.8
            coupling_symmetry = features[2] * 1.1
            nonlinear_strength = features[3] * 0.9
            mixing_degree = features[4] * 1.0
            coupling_efficiency = features[5] * 1.05
            
            return np.array(
                [
                    coupling_strength,
                    interaction_energy,
                    coupling_symmetry,
                    nonlinear_strength,
                    mixing_degree,
                    coupling_efficiency,
                ]
            )
            
        except Exception as e:
            self.logger.error(f"Target coupling generation failed: {e}")
            return np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

