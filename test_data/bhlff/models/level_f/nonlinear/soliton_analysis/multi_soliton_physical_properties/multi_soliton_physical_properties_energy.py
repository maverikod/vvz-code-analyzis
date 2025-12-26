"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Energy computation methods for multi-soliton physical properties.

This module provides energy computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class MultiSolitonPhysicalPropertiesEnergyMixin:
    """Mixin providing energy computation methods."""
    
    def _compute_individual_soliton_energy(
        self, profile: np.ndarray, x: np.ndarray
    ) -> float:
        """Compute energy of individual soliton."""
        try:
            # Kinetic energy
            kinetic_energy = 0.5 * np.trapz(np.gradient(profile) ** 2, x)
            
            # Potential energy
            potential_energy = 0.5 * self.lambda_param * np.trapz(profile**2, x)
            
            return kinetic_energy + potential_energy
        
        except Exception as e:
            self.logger.error(f"Individual soliton energy computation failed: {e}")
            return 0.0
    
    def _compute_interaction_energy(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """Compute interaction energy between solitons."""
        try:
            distance = abs(pos2 - pos1)
            interaction_range = width1 + width2
            
            # Step resonator interaction energy
            if distance < interaction_range:
                return self.interaction_strength * amp1 * amp2
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Interaction energy computation failed: {e}")
            return 0.0
    
    def _compute_three_body_interaction_energy(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> float:
        """Compute three-body interaction energy."""
        try:
            # Compute distances between all solitons
            distance_12 = abs(pos2 - pos1)
            distance_13 = abs(pos3 - pos1)
            distance_23 = abs(pos3 - pos2)
            
            # Compute interaction range for three-body interaction
            interaction_range = width1 + width2 + width3
            
            # Three-body interaction using step resonator theory
            total_distance = distance_12 + distance_13 + distance_23
            if total_distance < interaction_range:
                return self.three_body_strength * amp1 * amp2 * amp3
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Three-body interaction energy computation failed: {e}")
            return 0.0
    
    def _compute_interaction_efficiency(self, solution: Dict[str, Any]) -> float:
        """Compute interaction efficiency."""
        try:
            overlap_integral = solution.get("overlap_integral", 0.0)
            total_field_energy = solution.get("total_field_energy", 1.0)
            
            if total_field_energy > 0:
                return overlap_integral / total_field_energy
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Interaction efficiency computation failed: {e}")
            return 0.0

