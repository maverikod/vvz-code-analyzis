"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Single-particle potential computation.

This module provides methods for computing single-particle potentials
in multi-particle systems.

Physical Meaning:
    Computes potential contributions from individual particles
    in the multi-particle system.
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_structures import Particle


class SingleParticlePotentialComputation:
    """
    Single-particle potential computation.
    
    Physical Meaning:
        Provides methods for computing single-particle potentials.
    """
    
    def __init__(self, domain, system_params, step_potential_func):
        """
        Initialize single-particle potential computation.
        
        Args:
            domain: Domain parameters.
            system_params: System parameters.
            step_potential_func: Step potential function.
        """
        self.domain = domain
        self.system_params = system_params
        self._step_interaction_potential = step_potential_func
    
    def compute_single_particle_potential(self, particle: "Particle") -> np.ndarray:
        """
        Compute single-particle potential.
        
        Physical Meaning:
            Computes potential contribution from single particle
            in the multi-particle system.
            
        Args:
            particle (Particle): Particle object.
            
        Returns:
            np.ndarray: Single-particle potential field.
        """
        # Create coordinate arrays
        x = np.linspace(0, self.domain.L, self.domain.N)
        y = np.linspace(0, self.domain.L, self.domain.N)
        z = np.linspace(0, self.domain.L, self.domain.N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        # Calculate distance from particle
        distances = np.sqrt(
            (X - particle.position[0]) ** 2
            + (Y - particle.position[1]) ** 2
            + (Z - particle.position[2]) ** 2
        )
        
        # Create single-particle potential
        potential = self.create_single_particle_potential(distances, particle)
        
        return potential
    
    def create_single_particle_potential(
        self, distances: np.ndarray, particle: "Particle"
    ) -> np.ndarray:
        """
        Create single-particle potential.
        
        Physical Meaning:
            Creates potential field from single particle
            based on distance calculations.
            
        Args:
            distances (np.ndarray): Distance field from particle.
            particle (Particle): Particle object.
            
        Returns:
            np.ndarray: Single-particle potential field.
        """
        # Create potential based on particle properties using step resonator model
        potential = particle.charge * self._step_interaction_potential(distances)
        
        return potential

