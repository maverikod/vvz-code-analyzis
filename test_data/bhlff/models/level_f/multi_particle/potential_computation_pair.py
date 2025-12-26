"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pair interaction potential computation.

This module provides methods for computing pair interaction potentials
in multi-particle systems.

Physical Meaning:
    Computes potential contributions from pair interactions
    between particles in the multi-particle system.
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_structures import Particle


class PairInteractionPotentialComputation:
    """
    Pair interaction potential computation.
    
    Physical Meaning:
        Provides methods for computing pair interaction potentials.
    """
    
    def __init__(self, domain, system_params, step_three_body_func):
        """
        Initialize pair interaction potential computation.
        
        Args:
            domain: Domain parameters.
            system_params: System parameters.
            step_three_body_func: Step three-body potential function.
        """
        self.domain = domain
        self.system_params = system_params
        self._step_three_body_interaction_potential = step_three_body_func
    
    def compute_pair_interaction(
        self, particle_i: "Particle", particle_j: "Particle"
    ) -> np.ndarray:
        """
        Compute pair interaction potential.
        
        Physical Meaning:
            Computes potential contribution from pair interaction
            between two particles.
            
        Args:
            particle_i (Particle): First particle.
            particle_j (Particle): Second particle.
            
        Returns:
            np.ndarray: Pair interaction potential field.
        """
        # Create coordinate arrays
        x = np.linspace(0, self.domain.L, self.domain.N)
        y = np.linspace(0, self.domain.L, self.domain.N)
        z = np.linspace(0, self.domain.L, self.domain.N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        # Calculate distances from both particles
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
        
        # Create pair potential
        potential = self.create_pair_potential(
            distances_i, distances_j, particle_i, particle_j
        )
        
        return potential
    
    def create_pair_potential(
        self,
        distances_i: np.ndarray,
        distances_j: np.ndarray,
        particle_i: "Particle",
        particle_j: "Particle",
    ) -> np.ndarray:
        """
        Create pair potential.
        
        Physical Meaning:
            Creates potential field from pair interaction
            between two particles.
            
        Args:
            distances_i (np.ndarray): Distance field from particle i.
            distances_j (np.ndarray): Distance field from particle j.
            particle_i (Particle): First particle.
            particle_j (Particle): Second particle.
            
        Returns:
            np.ndarray: Pair potential field.
        """
        # Create pair potential based on particle interactions
        interaction_strength = particle_i.charge * particle_j.charge
        potential = interaction_strength * self._step_three_body_interaction_potential(
            distances_i, distances_j
        )
        
        return potential

