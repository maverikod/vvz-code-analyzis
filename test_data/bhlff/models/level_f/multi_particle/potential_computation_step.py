"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step resonator potential functions.

This module provides step function potential implementations
for particle interactions according to 7D BVP theory.

Physical Meaning:
    Implements step resonator model for particle interactions instead of
    exponential decay. This follows 7D BVP theory principles where
    interactions occur through semi-transparent boundaries.
"""

import numpy as np
from typing import Union


class StepResonatorPotentialFunctions:
    """
    Step resonator potential functions.
    
    Physical Meaning:
        Provides step function potential implementations
        for particle interactions.
    """
    
    def __init__(self, system_params):
        """
        Initialize step resonator potential functions.
        
        Args:
            system_params: System parameters.
        """
        self.system_params = system_params
    
    def step_interaction_potential(
        self, distance: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        """
        Step function interaction potential.
        
        Physical Meaning:
            Implements step resonator model for particle interactions instead of
            exponential decay. This follows 7D BVP theory principles where
            interactions occur through semi-transparent boundaries.
            
        Mathematical Foundation:
            V(r) = V₀ * Θ(r_cutoff - r) where Θ is the Heaviside step function
            and r_cutoff is the interaction cutoff distance.
            
        Args:
            distance: Distance between particles (scalar or array).
            
        Returns:
            Step function interaction potential.
        """
        # Step resonator parameters
        interaction_cutoff = self.system_params.interaction_range
        interaction_strength = self.system_params.get("interaction_strength", 1.0)
        
        # Step function interaction: 1.0 below cutoff, 0.0 above
        if isinstance(distance, np.ndarray):
            return np.where(distance < interaction_cutoff, interaction_strength, 0.0)
        else:
            return interaction_strength if distance < interaction_cutoff else 0.0
    
    def step_three_body_interaction_potential(
        self, distance_i: Union[float, np.ndarray], distance_j: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        """
        Step function three-body interaction potential.
        
        Physical Meaning:
            Implements step resonator model for three-body interactions instead of
            exponential decay. This follows 7D BVP theory principles where
            multi-body interactions occur through semi-transparent boundaries.
            
        Mathematical Foundation:
            V(r₁,r₂) = V₀ * Θ(r_cutoff - r₁) * Θ(r_cutoff - r₂) where Θ is the Heaviside step function
            and r_cutoff is the interaction cutoff distance.
            
        Args:
            distance_i: Distance to first particle (scalar or array).
            distance_j: Distance to second particle (scalar or array).
            
        Returns:
            Step function three-body interaction potential.
        """
        # Step resonator parameters
        interaction_cutoff = self.system_params.interaction_range
        interaction_strength = self.system_params.get("interaction_strength", 1.0)
        
        # Step function three-body interaction: 1.0 if both distances below cutoff, 0.0 otherwise
        if isinstance(distance_i, np.ndarray) or isinstance(distance_j, np.ndarray):
            condition = (distance_i < interaction_cutoff) & (
                distance_j < interaction_cutoff
            )
            return np.where(condition, interaction_strength, 0.0)
        else:
            if distance_i < interaction_cutoff and distance_j < interaction_cutoff:
                return interaction_strength
            else:
                return 0.0
    
    def step_three_particle_interaction_potential(
        self,
        distances_i: np.ndarray,
        distances_j: np.ndarray,
        distances_k: np.ndarray,
    ) -> np.ndarray:
        """
        Step function three-particle interaction potential.
        
        Physical Meaning:
            Implements step resonator model for three-particle interactions instead of
            exponential decay. This follows 7D BVP theory principles where
            multi-particle interactions occur through semi-transparent boundaries.
            
        Mathematical Foundation:
            V(r₁,r₂,r₃) = V₀ * Θ(r_cutoff - r₁) * Θ(r_cutoff - r₂) * Θ(r_cutoff - r₃)
            where Θ is the Heaviside step function and r_cutoff is the interaction cutoff distance.
            
        Args:
            distances_i: Distance field to first particle.
            distances_j: Distance field to second particle.
            distances_k: Distance field to third particle.
            
        Returns:
            Step function three-particle interaction potential field.
        """
        # Step resonator parameters
        interaction_cutoff = self.system_params.interaction_range
        
        # Step function three-particle interaction: 1.0 if all distances below cutoff, 0.0 otherwise
        step_condition = (
            (distances_i < interaction_cutoff)
            & (distances_j < interaction_cutoff)
            & (distances_k < interaction_cutoff)
        )
        
        return np.where(step_condition, 1.0, 0.0)
    
    def calculate_interaction_strength(self, distance: float) -> float:
        """
        Calculate interaction strength.
        
        Physical Meaning:
            Calculates interaction strength between particles
            based on distance.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Interaction strength.
        """
        # Simplified interaction strength calculation
        # In practice, this would involve proper interaction calculation
        if distance < self.system_params.interaction_range:
            return self.step_interaction_potential(distance)
        else:
            return 0.0

