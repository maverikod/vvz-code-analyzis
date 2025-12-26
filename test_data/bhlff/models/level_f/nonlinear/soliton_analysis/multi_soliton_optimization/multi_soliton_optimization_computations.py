"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Computation methods for multi-soliton optimization.

This module provides computation methods for interactions and energy as a mixin class.
"""

import numpy as np


class MultiSolitonOptimizationComputationsMixin:
    """Mixin providing computation methods."""
    
    def _compute_soliton_interaction_strength(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """
        Compute soliton interaction strength using 7D BVP theory.
        
        Physical Meaning:
            Computes the interaction strength between two solitons
            using 7D BVP step resonator theory instead of exponential
            decay interactions.
            
        Mathematical Foundation:
            Interaction strength based on step resonator overlap:
            I = A₁A₂ * step_resonator(distance, width₁ + width₂)
            where step_resonator implements 7D BVP theory.
            
        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            
        Returns:
            float: Interaction strength.
        """
        try:
            # Compute distance between solitons
            distance = abs(pos2 - pos1)
            
            # Compute interaction range
            interaction_range = width1 + width2
            
            # Compute step resonator interaction strength
            if distance < interaction_range:
                interaction_strength = amp1 * amp2 * getattr(
                    self, "interaction_strength", 1.0
                )
            else:
                interaction_strength = 0.0
            
            return interaction_strength
        
        except Exception as e:
            self.logger.error(f"Soliton interaction strength computation failed: {e}")
            return 0.0
    
    def _compute_field_energy(self, profile: np.ndarray, x: np.ndarray) -> float:
        """
        Compute field energy according to 7D BVP theory.
        
        Physical Meaning:
            Computes the field energy instead of mass according to 7D BVP theory
            principles where energy is the fundamental quantity rather than mass.
            
        Mathematical Foundation:
            Field energy = ∫ |∇a|² dx where a is the field amplitude
            and ∇a is the field gradient.
            
        Args:
            profile (np.ndarray): Field profile.
            x (np.ndarray): Spatial coordinates.
            
        Returns:
            float: Field energy according to 7D BVP theory.
        """
        # Compute field gradient
        field_gradient = np.gradient(profile, x)
        
        # Compute field energy density
        energy_density = np.abs(field_gradient) ** 2
        
        # Integrate over space
        field_energy = np.trapz(energy_density, x)
        
        return field_energy

