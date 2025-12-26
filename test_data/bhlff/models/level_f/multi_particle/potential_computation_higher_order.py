"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Higher-order interaction potential computation.

This module provides methods for computing higher-order interaction potentials
in multi-particle systems.

Physical Meaning:
    Computes potential contributions from higher-order interactions
    (three-particle and beyond) in the multi-particle system.
"""

import numpy as np
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .data_structures import Particle


class HigherOrderInteractionComputation:
    """
    Higher-order interaction potential computation.
    
    Physical Meaning:
        Provides methods for computing higher-order interaction potentials.
    """
    
    def __init__(self, domain, system_params, step_three_particle_func):
        """
        Initialize higher-order interaction computation.
        
        Args:
            domain: Domain parameters.
            system_params: System parameters.
            step_three_particle_func: Step three-particle potential function.
        """
        self.domain = domain
        self.system_params = system_params
        self._step_three_particle_interaction_potential = step_three_particle_func
    
    def compute_higher_order_interactions(
        self, particles: List["Particle"]
    ) -> np.ndarray:
        """
        Compute higher-order interactions.
        
        Physical Meaning:
            Computes potential contribution from higher-order
            interactions in the multi-particle system.
            
        Returns:
            np.ndarray: Higher-order interaction potential field.
        """
        # Initialize potential
        potential = np.zeros(self.domain.shape)
        
        # Compute three-particle interactions
        for i, particle_i in enumerate(particles):
            for j, particle_j in enumerate(particles[i + 1 :], i + 1):
                for k, particle_k in enumerate(particles[j + 1 :], j + 1):
                    three_particle_potential = self.compute_three_particle_interaction(
                        particle_i, particle_j, particle_k
                    )
                    potential += three_particle_potential
        
        return potential
    
    def compute_three_particle_interaction(
        self, particle_i: "Particle", particle_j: "Particle", particle_k: "Particle"
    ) -> np.ndarray:
        """
        Compute three-particle interaction potential.
        
        Physical Meaning:
            Computes potential contribution from three-particle
            interaction in the multi-particle system.
            
        Args:
            particle_i (Particle): First particle.
            particle_j (Particle): Second particle.
            particle_k (Particle): Third particle.
            
        Returns:
            np.ndarray: Three-particle interaction potential field.
        """
        # Create coordinate arrays
        x = np.linspace(0, self.domain.L, self.domain.N)
        y = np.linspace(0, self.domain.L, self.domain.N)
        z = np.linspace(0, self.domain.L, self.domain.N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        # Calculate distances from all three particles
        distances_i = np.sqrt(
            (X - particle_i.position[0]) ** 2
            + (Y - particle_i.position[1]) ** 2
            + (Z - particle_i.position[2]) ** 2
        )
        
        distances_j = np.sqrt(
            (X - particle_j.position[0]) ** 2
            + (Y - particle_j.position[1]) ** 2
            + (Z - particle_j.position[2]) ** 2
        )
        
        distances_k = np.sqrt(
            (X - particle_k.position[0]) ** 2
            + (Y - particle_k.position[1]) ** 2
            + (Z - particle_k.position[2]) ** 2
        )
        
        # Create three-particle potential
        potential = self.create_higher_order_potential(
            distances_i, distances_j, distances_k, particle_i, particle_j, particle_k
        )
        
        return potential
    
    def create_higher_order_potential(
        self,
        distances_i: np.ndarray,
        distances_j: np.ndarray,
        distances_k: np.ndarray,
        particle_i: "Particle",
        particle_j: "Particle",
        particle_k: "Particle",
    ) -> np.ndarray:
        """
        Create higher-order potential.
        
        Physical Meaning:
            Creates potential field from higher-order interaction
            between three particles.
            
        Args:
            distances_i (np.ndarray): Distance field from particle i.
            distances_j (np.ndarray): Distance field from particle j.
            distances_k (np.ndarray): Distance field from particle k.
            particle_i (Particle): First particle.
            particle_j (Particle): Second particle.
            particle_k (Particle): Third particle.
            
        Returns:
            np.ndarray: Higher-order potential field.
        """
        # Create higher-order potential based on three-particle interaction
        interaction_strength = (
            particle_i.charge * particle_j.charge * particle_k.charge
        )
        potential = (
            interaction_strength
            * self._step_three_particle_interaction_potential(
                distances_i, distances_j, distances_k
            )
        )
        
        return potential

