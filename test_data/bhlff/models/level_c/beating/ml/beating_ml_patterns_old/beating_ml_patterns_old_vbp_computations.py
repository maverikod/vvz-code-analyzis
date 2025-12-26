"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

VBP envelope computation methods for beating ML patterns old.

This module provides VBP envelope computation methods as a mixin class.
"""

import numpy as np


class BeatingMLPatternsOldVBPComputationsMixin:
    """Mixin providing VBP envelope computation methods."""
    
    def _compute_vbp_envelope_symmetry(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope symmetry.
        
        Physical Meaning:
            Computes VBP envelope symmetry based on envelope properties.
        """
        # Compute envelope symmetry using spatial correlation
        center = envelope.shape[0] // 2
        left_half = envelope[:center]
        right_half = envelope[center:]
        
        if left_half.shape != right_half.shape:
            return 0.5
        
        correlation = np.corrcoef(left_half.flatten(), right_half.flatten())[0, 1]
        return max(0.0, min(1.0, correlation))
    
    def _compute_vbp_envelope_regularity(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope regularity.
        
        Physical Meaning:
            Computes VBP envelope regularity based on envelope properties.
        """
        # Compute envelope regularity using variance analysis
        envelope_abs = np.abs(envelope)
        local_variance = np.var(envelope_abs)
        global_variance = np.var(envelope_abs.flatten())
        
        if global_variance == 0:
            return 1.0
        
        regularity = 1.0 - (local_variance / global_variance)
        return max(0.0, min(1.0, regularity))
    
    def _compute_vbp_envelope_complexity(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope complexity.
        
        Physical Meaning:
            Computes VBP envelope complexity based on envelope properties.
        """
        # Compute envelope complexity using frequency content
        envelope_fft = np.fft.fftn(envelope)
        frequency_spectrum = np.abs(envelope_fft)
        
        # Count significant frequency components
        threshold = 0.1 * np.max(frequency_spectrum)
        significant_components = np.sum(frequency_spectrum > threshold)
        total_components = frequency_spectrum.size
        
        complexity = significant_components / total_components
        return max(0.0, min(1.0, complexity))
    
    def _combine_7d_symmetries(
        self, phase_field_symmetry: float, vbp_symmetry: float
    ) -> float:
        """
        Combine 7D symmetries using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope symmetries using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_symmetry * 0.7 + vbp_symmetry * 0.3
    
    def _combine_7d_regularities(
        self, phase_field_regularity: float, vbp_regularity: float
    ) -> float:
        """
        Combine 7D regularities using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope regularities using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_regularity * 0.7 + vbp_regularity * 0.3
    
    def _combine_7d_complexities(
        self, phase_field_complexity: float, vbp_complexity: float
    ) -> float:
        """
        Combine 7D complexities using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope complexities using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_complexity * 0.7 + vbp_complexity * 0.3

