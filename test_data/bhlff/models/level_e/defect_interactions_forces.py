"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Force and potential computation for defect interactions.

This module provides methods for computing interaction forces and
potentials between topological defects.

Physical Meaning:
    Computes forces and potentials between defects based on their
    charges and separations using fractional Green functions.
"""

import numpy as np
from typing import List


class DefectInteractionsForces:
    """
    Force and potential computation for defect interactions.
    
    Physical Meaning:
        Provides methods for computing interaction forces and
        potentials between defects.
    """
    
    def __init__(self, params: dict, green_computation):
        """
        Initialize force computation.
        
        Args:
            params (dict): Physical parameters.
            green_computation: Green function computation instance.
        """
        self.params = params
        self.green_computation = green_computation
        self.cutoff_radius = params.get("cutoff_radius", 0.1)
    
    def compute_interaction_forces(
        self, positions: List[np.ndarray], charges: List[int]
    ) -> List[np.ndarray]:
        """
        Compute interaction forces between defects.
        
        Physical Meaning:
            Calculates the forces acting on each defect due to
            interactions with all other defects in the system.
            
        Mathematical Foundation:
            Fᵢ = -∇ᵢ Σⱼ qᵢqⱼ G(rᵢⱼ) where G is the Green function
            and the sum is over all other defects j ≠ i.
            
        Args:
            positions: List of defect positions
            charges: List of defect charges
            
        Returns:
            List of force vectors for each defect
        """
        n_defects = len(positions)
        forces = [np.zeros(3) for _ in range(n_defects)]
        
        # Compute pairwise interactions
        for i in range(n_defects):
            for j in range(n_defects):
                if i != j:
                    # Compute separation vector
                    r_ij = positions[j] - positions[i]
                    r_magnitude = np.linalg.norm(r_ij)
                    
                    # Skip if defects are too close
                    if r_magnitude < self.cutoff_radius:
                        continue
                    
                    # Compute interaction force
                    force_ij = self.compute_pair_force(
                        r_ij, r_magnitude, charges[i], charges[j]
                    )
                    forces[i] += force_ij
        
        return forces
    
    def compute_pair_force(
        self, r_ij: np.ndarray, r_magnitude: float, charge_i: int, charge_j: int
    ) -> np.ndarray:
        """
        Compute force between defect pair.
        
        Physical Meaning:
            Calculates the force between two defects based on
            their charges and separation.
            
        Mathematical Foundation:
            F = -qᵢqⱼ ∇G(r) where G is the Green function.
            
        Args:
            r_ij: Separation vector from defect i to defect j
            r_magnitude: Magnitude of separation
            charge_i: Charge of defect i
            charge_j: Charge of defect j
            
        Returns:
            Force vector on defect i due to defect j
        """
        # Compute Green function and its gradient
        green_value, green_gradient = self.green_computation.compute_green_function(
            r_magnitude
        )
        
        # Force magnitude
        force_magnitude = charge_i * charge_j * green_gradient
        
        # Force direction (along separation vector)
        if r_magnitude > 1e-10:
            force_direction = r_ij / r_magnitude
        else:
            force_direction = np.zeros(3)
        
        # Total force
        force = force_magnitude * force_direction
        
        return force
    
    def compute_interaction_potential(
        self, positions: List[np.ndarray], charges: List[int]
    ) -> float:
        """
        Compute total interaction potential energy.
        
        Physical Meaning:
            Calculates the total potential energy of the defect
            system due to all pairwise interactions.
            
        Mathematical Foundation:
            U = (1/2) Σᵢⱼ qᵢqⱼ G(rᵢⱼ) where the factor 1/2 avoids
            double counting.
            
        Args:
            positions: List of defect positions
            charges: List of defect charges
            
        Returns:
            Total interaction potential energy
        """
        n_defects = len(positions)
        total_potential = 0.0
        
        # Compute pairwise interactions
        for i in range(n_defects):
            for j in range(i + 1, n_defects):
                # Compute separation
                r_ij = positions[j] - positions[i]
                r_magnitude = np.linalg.norm(r_ij)
                
                # Skip if defects are too close
                if r_magnitude < self.cutoff_radius:
                    continue
                
                # Compute Green function
                green_value, _ = self.green_computation.compute_green_function(
                    r_magnitude
                )
                
                # Add to total potential
                total_potential += charges[i] * charges[j] * green_value
        
        return total_potential

