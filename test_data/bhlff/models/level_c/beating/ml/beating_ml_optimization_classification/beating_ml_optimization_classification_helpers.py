"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for beating ML optimization classification.

This module provides helper methods as a mixin class.
"""

import numpy as np


class BeatingMLOptimizationClassificationHelpersMixin:
    """Mixin providing helper methods."""
    
    def _compute_spectral_entropy(self, envelope: np.ndarray) -> float:
        """
        Compute spectral entropy using 7D BVP theory.
        
        Physical Meaning:
            Computes spectral entropy of the envelope field using
            7D phase field theory and VBP envelope analysis.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Spectral entropy.
        """
        # Compute FFT of envelope
        fft_envelope = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_envelope) ** 2
        
        # Normalize power spectrum
        power_spectrum = power_spectrum / np.sum(power_spectrum)
        
        # Compute spectral entropy
        entropy = -np.sum(power_spectrum * np.log(power_spectrum + 1e-10))
        
        return entropy
    
    def _compute_phase_coherence(self, envelope: np.ndarray) -> float:
        """
        Compute phase coherence using 7D BVP theory.
        
        Physical Meaning:
            Computes phase coherence of the envelope field using
            7D phase field theory and VBP envelope analysis.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Phase coherence.
        """
        # Compute phase of envelope
        phase = np.angle(envelope)
        
        # Compute phase coherence as correlation between adjacent phases
        if phase.size > 1:
            phase_diff = np.diff(phase.flatten())
            coherence = np.abs(np.mean(np.exp(1j * phase_diff)))
        else:
            coherence = 1.0
        
        return coherence

