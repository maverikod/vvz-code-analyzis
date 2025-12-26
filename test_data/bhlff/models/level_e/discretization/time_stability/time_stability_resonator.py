"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonator methods for time stability analyzer.

This module provides step resonator methods as a mixin class.
"""

import numpy as np


class TimeStabilityResonatorMixin:
    """Mixin providing step resonator methods."""
    
    def _step_resonator_phase_field(self, x: np.ndarray, sigma: float) -> np.ndarray:
        """
        Step resonator phase field according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function phase field instead of Gaussian field
            according to 7D BVP theory principles where field boundaries
            are determined by step functions rather than smooth transitions.
            
        Mathematical Foundation:
            Field = Θ(sigma - |x|) where Θ is the Heaviside step function
            and sigma is the field width parameter.
            
        Args:
            x (np.ndarray): Spatial coordinates.
            sigma (float): Field width parameter.
            
        Returns:
            np.ndarray: Step function phase field according to 7D BVP theory.
        """
        # Step function phase field according to 7D BVP theory
        cutoff_distance = sigma
        field_strength = 1.0
        
        # Apply step function boundary condition
        field = field_strength * np.where(np.abs(x) < cutoff_distance, 1.0, 0.0)
        
        return field
    
    def _step_resonator_time_evolution(self, T: float) -> float:
        """
        Step resonator time evolution according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function time evolution instead of exponential decay
            according to 7D BVP theory principles where time evolution
            is determined by step functions rather than smooth transitions.
            
        Mathematical Foundation:
            Evolution = Θ(T_cutoff - T) where Θ is the Heaviside step function
            and T_cutoff is the cutoff time for evolution.
            
        Args:
            T (float): Time parameter.
            
        Returns:
            float: Step function time evolution according to 7D BVP theory.
        """
        # Step function time evolution according to 7D BVP theory
        cutoff_time = 2.0
        evolution_strength = 1.0
        
        # Apply step function boundary condition
        if T < cutoff_time:
            return evolution_strength
        else:
            return 0.0

