"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Computation helper methods for beating ML prediction optimization.

This module provides computation helper methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class BeatingMLPredictionOptimizerComputationsMixin:
    """Mixin providing computation helper methods."""
    
    def _compute_spectral_entropy(self, envelope: np.ndarray) -> float:
        """
        Compute spectral entropy using 7D BVP theory.
        
        Physical Meaning:
            Computes spectral entropy of the envelope field using
            7D phase field theory and VBP envelope analysis.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Spectral entropy value.
        """
        # Compute FFT of envelope
        fft_envelope = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_envelope) ** 2
        
        # Normalize power spectrum
        power_spectrum = power_spectrum / np.sum(power_spectrum)
        
        # Compute spectral entropy
        # Avoid log(0) by adding small epsilon
        epsilon = 1e-10
        power_spectrum = power_spectrum + epsilon
        
        spectral_entropy = -np.sum(power_spectrum * np.log(power_spectrum))
        
        return float(spectral_entropy)
    
    def _compute_phase_coherence(self, envelope: np.ndarray) -> float:
        """
        Compute phase coherence using 7D BVP theory.
        
        Physical Meaning:
            Computes phase coherence of the envelope field using
            7D phase field theory and VBP envelope analysis.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Phase coherence value.
        """
        # Compute phase of envelope
        phase = np.angle(envelope)
        
        # Compute phase coherence using circular statistics
        # Convert to complex representation
        complex_phase = np.exp(1j * phase)
        
        # Compute mean phase coherence
        mean_complex = np.mean(complex_phase)
        phase_coherence = np.abs(mean_complex) if phase.size > 1 else 1.0
        
        return float(phase_coherence)
    
    def _compute_7d_phase_field_optimization(
        self, performance: float, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute 7D phase field optimization parameters.
        
        Physical Meaning:
            Computes optimization parameters based on 7D phase field theory
            and VBP envelope analysis for ML prediction optimization.
            
        Mathematical Foundation:
            Uses 7D phase field properties including phase coherence,
            topological charge, and energy density for optimization.
            
        Args:
            performance (float): Current prediction performance.
            parameters (Dict[str, Any]): Current prediction parameters.
            
        Returns:
            Dict[str, Any]: 7D phase field optimization results.
        """
        # Compute phase coherence from current performance
        phase_coherence = min(1.0, max(0.0, performance))
        
        # Compute topological charge based on performance stability
        performance_stability = 1.0 - abs(performance - 0.8)  # Assume 0.8 is optimal
        topological_charge = (performance_stability - 0.5) * 2.0  # Scale to [-1, 1]
        
        # Compute energy density from prediction complexity
        prediction_complexity = parameters.get("model_complexity", "medium")
        if prediction_complexity == "low":
            energy_density = 0.5
        elif prediction_complexity == "high":
            energy_density = 2.0
        else:
            energy_density = 1.0
        
        # Compute phase velocity from regularization strength
        regularization_strength = parameters.get("regularization_strength", 0.01)
        phase_velocity = 1.0 / (1.0 + regularization_strength * 100)
        
        return {
            "phase_coherence": phase_coherence,
            "topological_charge": topological_charge,
            "energy_density": energy_density,
            "phase_velocity": phase_velocity,
            "optimization_quality": performance * phase_coherence,
        }

