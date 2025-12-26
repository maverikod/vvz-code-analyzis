"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for pattern feature extraction.

This module provides helper methods for computing topological charge,
energy symmetry, and other auxiliary computations.

Physical Meaning:
    Provides helper methods for pattern feature extraction including
    topological charge computation and energy symmetry analysis.
"""

import numpy as np


class PatternFeatureHelpers:
    """
    Helper methods for pattern feature extraction.
    
    Physical Meaning:
        Provides helper methods for pattern feature extraction.
    """
    
    def compute_topological_charge(self, envelope: np.ndarray) -> float:
        """
        Compute topological charge using 7D phase field theory.
        
        Physical Meaning:
            Computes topological charge based on 7D phase field theory.
        """
        # Compute phase gradient
        phase = np.angle(envelope)
        grad_x = np.gradient(phase, axis=1)
        grad_y = np.gradient(phase, axis=0)
        
        # Compute topological charge
        topological_charge = np.sum(grad_x * grad_y) / (2 * np.pi)
        
        return float(topological_charge)
    
    def compute_energy_symmetry(self, energy_density: np.ndarray) -> float:
        """
        Compute energy density symmetry.
        
        Physical Meaning:
            Computes energy density symmetry based on spatial distribution.
        """
        # Compute energy density symmetry using spatial correlation
        center = energy_density.shape[0] // 2
        left_half = energy_density[:center]
        right_half = energy_density[center:]
        
        if left_half.shape != right_half.shape:
            return 0.5
        
        correlation = np.corrcoef(left_half.flatten(), right_half.flatten())[0, 1]
        return max(0.0, min(1.0, correlation))

