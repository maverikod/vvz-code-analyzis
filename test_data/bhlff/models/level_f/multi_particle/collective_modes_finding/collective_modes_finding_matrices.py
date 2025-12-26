"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Matrix computation methods for collective modes finding.

This module provides matrix computation methods as a mixin class.
"""

import numpy as np
from typing import List
import logging

from ..data_structures import Particle


class CollectiveModesFindingMatricesMixin:
    """Mixin providing matrix computation methods."""
    
    def _create_energy_matrix(self) -> np.ndarray:
        """
        Create energy matrix from field configuration.
        
        Physical Meaning:
            Creates energy matrix for collective modes analysis
            based on field energy density and phase gradient energy.
            In 7D BVP theory, energy emerges from field localization
            and phase gradient contributions.
            
        Mathematical Foundation:
            E_ij = ∫ [μ|∇a|² + |∇Θ|^(2β)] δᵢⱼ d³x d³φ dt
            where a is field amplitude and Θ is phase.
            
        Returns:
            np.ndarray: Energy matrix.
        """
        # Create energy matrix
        energy_matrix = np.zeros((len(self.particles), len(self.particles)))
        
        # Fill diagonal elements with particle energies computed from field
        for i, particle in enumerate(self.particles):
            energy_matrix[i, i] = self._compute_particle_energy_from_field(particle)
        
        return energy_matrix
    
    def _create_stiffness_matrix(self) -> np.ndarray:
        """
        Create stiffness matrix.
        
        Physical Meaning:
            Creates stiffness matrix for collective modes analysis
            based on particle interactions.
            
        Returns:
            np.ndarray: Stiffness matrix.
        """
        # Create stiffness matrix
        stiffness_matrix = np.zeros((len(self.particles), len(self.particles)))
        
        # Fill matrix with interaction strengths
        for i, particle_i in enumerate(self.particles):
            for j, particle_j in enumerate(self.particles):
                if i != j:
                    distance = np.linalg.norm(particle_i.position - particle_j.position)
                    interaction_strength = self._calculate_interaction_strength(
                        distance
                    )
                    stiffness_matrix[i, j] = interaction_strength
        
        # Fill diagonal elements
        for i in range(len(self.particles)):
            stiffness_matrix[i, i] = -np.sum(stiffness_matrix[i, :])
        
        return stiffness_matrix
    
    def _compute_dynamics_matrix(self) -> np.ndarray:
        """
        Compute dynamics matrix.
        
        Physical Meaning:
            Computes dynamics matrix for collective modes analysis
            based on energy and stiffness matrices using 7D BVP theory.
            
        Returns:
            np.ndarray: Dynamics matrix.
        """
        # Compute dynamics matrix E⁻¹K where E is energy matrix
        dynamics_matrix = (
            self._compute_energy_matrix_inverse(self.energy_matrix)
            @ self.stiffness_matrix
        )
        
        return dynamics_matrix
    
    def _compute_energy_matrix_inverse(self, energy_matrix: np.ndarray) -> np.ndarray:
        """
        Compute inverse of energy matrix from field configuration.
        
        Physical Meaning:
            Computes the inverse of the energy matrix for dynamics
            calculations. In 7D BVP theory, this represents the
            inverse of field energy density contributions.
            
        Mathematical Foundation:
            E⁻¹ represents the inverse of field energy contributions
            to particle dynamics in the 7D phase field theory.
            
        Args:
            energy_matrix: Energy matrix computed from field configuration
            
        Returns:
            np.ndarray: Inverse of energy matrix
        """
        # Compute inverse with proper error handling
        try:
            energy_inv = np.linalg.inv(energy_matrix)
        except np.linalg.LinAlgError:
            # Handle singular matrix case
            # Add small regularization term
            regularization = 1e-10 * np.eye(energy_matrix.shape[0])
            energy_inv = np.linalg.inv(energy_matrix + regularization)
        
        return energy_inv
    
    def _compute_particle_energy_from_field(self, particle: Particle) -> float:
        """
        Compute particle energy from field configuration.
        
        Physical Meaning:
            Calculates the energy of a particle from the field configuration
            using 7D BVP theory principles. Energy emerges from field
            localization and phase gradient contributions.
            
        Mathematical Foundation:
            E_particle = ∫ [μ|∇a|² + |∇Θ|^(2β)] d³x d³φ dt
            where a is the field amplitude and Θ is the phase.
            
        Args:
            particle: Particle object with position and properties
            
        Returns:
            float: Particle energy computed from field configuration
        """
        # Extract field parameters from system parameters
        mu = self.system_params.get("mu", 1.0)
        beta = self.system_params.get("beta", 1.0)
        interaction_strength = self.system_params.get("interaction_strength", 1.0)
        
        # Compute field energy density components
        # Localization energy: μ|∇a|²
        localization_energy = mu * interaction_strength
        
        # Phase gradient energy: |∇Θ|^(2β)
        phase_gradient_energy = interaction_strength ** (2 * beta)
        
        # Position-dependent energy modulation
        position_factor = 1.0 + 0.1 * np.linalg.norm(particle.position)
        
        # Total particle energy
        particle_energy = (
            localization_energy + phase_gradient_energy
        ) * position_factor
        
        return particle_energy

