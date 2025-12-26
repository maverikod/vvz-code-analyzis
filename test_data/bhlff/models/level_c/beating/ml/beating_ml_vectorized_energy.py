"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized energy and momentum computation for ML prediction.

This module provides vectorized methods for computing energy, momentum,
angular momentum, and entropy in 7D phase field configurations.

Physical Meaning:
    Computes energy-related quantities of 7D phase field configurations
    using vectorized operations for efficient analysis.
"""

import numpy as np


class VectorizedEnergyComputation:
    """
    Vectorized energy and momentum computation.
    
    Physical Meaning:
        Provides vectorized methods for computing energy-related quantities.
    """
    
    def compute_7d_phase_field_energy_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute 7D phase field energy using vectorized operations.
        
        Physical Meaning:
            Computes total energy of 7D phase field configuration
            using vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized energy computation based on 7D phase field theory
            and VBP envelope energy density.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Total energy of the phase field.
        """
        # Vectorized energy computation
        energy_density = np.abs(envelope) ** 2
        total_energy = np.sum(energy_density)
        
        return float(total_energy)
    
    def compute_7d_phase_field_momentum_vectorized(
        self, envelope: np.ndarray
    ) -> np.ndarray:
        """
        Compute 7D phase field momentum using vectorized operations.
        
        Physical Meaning:
            Computes momentum of 7D phase field configuration
            using vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized momentum computation based on 7D phase field theory
            and VBP envelope momentum density.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            np.ndarray: Momentum vector of the phase field.
        """
        # Vectorized momentum computation
        if envelope.ndim >= 1:
            # Compute momentum along each axis
            momentum_components = []
            for axis in range(min(3, envelope.ndim)):  # Limit to 3D for efficiency
                axis_data = np.moveaxis(envelope, axis, 0)
                if axis_data.shape[0] > 1:
                    # Vectorized momentum computation
                    momentum = np.sum(np.abs(axis_data) ** 2)
                    momentum_components.append(momentum)
            
            return (
                np.array(momentum_components)
                if momentum_components
                else np.array([0.0])
            )
        
        return np.array([0.0])
    
    def compute_7d_phase_field_angular_momentum_vectorized(
        self, envelope: np.ndarray
    ) -> float:
        """
        Compute 7D phase field angular momentum using vectorized operations.
        
        Physical Meaning:
            Computes angular momentum of 7D phase field configuration
            using vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized angular momentum computation based on 7D phase field theory
            and VBP envelope angular momentum density.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Angular momentum of the phase field.
        """
        # Vectorized angular momentum computation
        if envelope.ndim >= 2:
            # Compute angular momentum using vectorized operations
            phase_field = np.angle(envelope)
            magnitude_field = np.abs(envelope)
            
            # Vectorized angular momentum computation
            angular_momentum = np.sum(phase_field * magnitude_field)
            
            return float(angular_momentum)
        
        return 0.0
    
    def compute_7d_phase_field_entropy_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute 7D phase field entropy using vectorized operations.
        
        Physical Meaning:
            Computes entropy of 7D phase field configuration
            using vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized entropy computation based on 7D phase field theory
            and VBP envelope entropy density.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Entropy of the phase field.
        """
        # Vectorized entropy computation
        magnitude_field = np.abs(envelope)
        
        # Normalize to probability distribution
        total_magnitude = np.sum(magnitude_field)
        if total_magnitude > 0:
            probability_dist = magnitude_field / total_magnitude
            
            # Vectorized entropy computation
            entropy = -np.sum(probability_dist * np.log(probability_dist + 1e-10))
            
            return float(entropy)
        
        return 0.0

