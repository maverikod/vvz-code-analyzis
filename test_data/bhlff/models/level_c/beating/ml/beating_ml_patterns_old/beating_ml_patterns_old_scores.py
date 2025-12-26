"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Score computation methods for beating ML patterns old.

This module provides score computation methods as a mixin class.
"""

import numpy as np


class BeatingMLPatternsOldScoresMixin:
    """Mixin providing score computation methods."""
    
    def _calculate_symmetry_score(self, envelope: np.ndarray) -> float:
        """
        Calculate symmetry score using 7D phase field theory.
        
        Physical Meaning:
            Computes symmetry score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
            
        Mathematical Foundation:
            Uses 7D phase field symmetry analysis including phase coherence,
            topological charge, and energy density distribution.
        """
        # Compute 7D phase field symmetry using full mathematical framework
        phase_field_symmetry = self._compute_7d_phase_field_symmetry(envelope)
        
        # Compute VBP envelope symmetry
        vbp_symmetry = self._compute_vbp_envelope_symmetry(envelope)
        
        # Combine symmetries using 7D phase field theory
        combined_symmetry = self._combine_7d_symmetries(
            phase_field_symmetry, vbp_symmetry
        )
        
        return max(0.0, min(1.0, combined_symmetry))
    
    def _calculate_regularity_score(self, envelope: np.ndarray) -> float:
        """
        Calculate regularity score using 7D phase field theory.
        
        Physical Meaning:
            Computes regularity score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
            
        Mathematical Foundation:
            Uses 7D phase field regularity analysis including phase coherence,
            topological charge, and energy density distribution.
        """
        # Compute 7D phase field regularity using full mathematical framework
        phase_field_regularity = self._compute_7d_phase_field_regularity(envelope)
        
        # Compute VBP envelope regularity
        vbp_regularity = self._compute_vbp_envelope_regularity(envelope)
        
        # Combine regularities using 7D phase field theory
        combined_regularity = self._combine_7d_regularities(
            phase_field_regularity, vbp_regularity
        )
        
        return max(0.0, min(1.0, combined_regularity))
    
    def _calculate_complexity_score(self, envelope: np.ndarray) -> float:
        """
        Calculate complexity score using 7D phase field theory.
        
        Physical Meaning:
            Computes complexity score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
            
        Mathematical Foundation:
            Uses 7D phase field complexity analysis including phase coherence,
            topological charge, and energy density distribution.
        """
        # Compute 7D phase field complexity using full mathematical framework
        phase_field_complexity = self._compute_7d_phase_field_complexity(envelope)
        
        # Compute VBP envelope complexity
        vbp_complexity = self._compute_vbp_envelope_complexity(envelope)
        
        # Combine complexities using 7D phase field theory
        combined_complexity = self._combine_7d_complexities(
            phase_field_complexity, vbp_complexity
        )
        
        return max(0.0, min(1.0, combined_complexity))

