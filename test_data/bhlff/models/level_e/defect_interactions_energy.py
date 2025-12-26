"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Energy computation for defect interactions.

This module provides methods for computing defect energy, annihilation
energy, and energy release rates for defect interaction calculations.

Physical Meaning:
    Computes energy-related quantities for defect interactions including
    defect energy from field configuration, annihilation energy, and
    energy release rates during defect-antidefect annihilation.
"""

import numpy as np
from typing import Dict, Any, List


class DefectInteractionsEnergy:
    """
    Energy computation for defect interactions.
    
    Physical Meaning:
        Provides methods for computing energy-related quantities
        for defect interactions.
    """
    
    def __init__(self, params: dict, green_computation):
        """
        Initialize energy computation.
        
        Args:
            params (dict): Physical parameters.
            green_computation: Green function computation instance.
        """
        self.params = params
        self.green_computation = green_computation
        self.screening_length = params.get("screening_length", 0.5)
    
    def compute_defect_energy_from_field(self) -> float:
        """
        Compute defect energy from field configuration.
        
        Physical Meaning:
            Calculates the energy of a defect from the field configuration
            using 7D BVP theory principles. Energy emerges from field
            localization and phase gradient contributions.
            
        Mathematical Foundation:
            E_defect = ∫ [μ|∇a|² + |∇Θ|^(2β)] d³x d³φ dt
            where a is the field amplitude and Θ is the phase.
            
        Returns:
            Defect energy computed from field configuration
        """
        # Extract field parameters
        mu = self.params.get("mu", 1.0)
        beta = self.params.get("beta", 1.0)
        interaction_strength = self.params.get("interaction_strength", 1.0)
        
        # Compute field energy density components
        # Localization energy: μ|∇a|²
        localization_energy = mu * interaction_strength
        
        # Phase gradient energy: |∇Θ|^(2β)
        phase_gradient_energy = interaction_strength ** (2 * beta)
        
        # Total defect energy
        defect_energy = localization_energy + phase_gradient_energy
        
        return defect_energy
    
    def compute_annihilation_energy(
        self, charge1: int, charge2: int, separation: float
    ) -> float:
        """
        Compute energy released during annihilation using fractional Green function.
        
        Physical Meaning:
            Calculates the energy released when a defect-antidefect
            pair annihilates, based on their charges and separation
            using the fractional Green function G_β(r).
            
        Mathematical Foundation:
            Energy scales with the fractional Green function value
            at the separation distance: E ∝ |q₁q₂| G_β(r).
            
        Args:
            charge1: Charge of first defect
            charge2: Charge of second defect
            separation: Separation distance
            
        Returns:
            Annihilation energy
        """
        # Energy scales with charge magnitude
        charge_factor = abs(charge1 * charge2)
        
        # Get Green function value at separation
        green_value, _ = self.green_computation.compute_green_function(separation)
        
        # Total annihilation energy from fractional Green function
        energy = charge_factor * green_value
        
        return energy
    
    def compute_energy_release_rate(self, annihilation_energy: float) -> float:
        """
        Compute rate of energy release during annihilation.
        
        Physical Meaning:
            Calculates how quickly energy is released during
            the annihilation process.
            
        Args:
            annihilation_energy: Total annihilation energy
            
        Returns:
            Energy release rate
        """
        # Energy release rate depends on annihilation energy
        release_rate = annihilation_energy / self.params.get("annihilation_time", 1.0)
        
        return release_rate
    
    def compute_relaxation_time(self, separation: float) -> float:
        """
        Compute field relaxation time after annihilation.
        
        Physical Meaning:
            Calculates the time required for the field to relax
            to its new configuration after defect annihilation.
            
        Args:
            separation: Initial separation of defects
            
        Returns:
            Relaxation time
        """
        # Relaxation time increases with initial separation
        base_time = self.params.get("base_relaxation_time", 0.1)
        separation_factor = 1.0 + separation / self.screening_length
        
        relaxation_time = base_time * separation_factor
        
        return relaxation_time
    
    def simulate_defect_annihilation(
        self, defect_pair: List[int], positions: List[np.ndarray], charges: List[int]
    ) -> Dict[str, Any]:
        """
        Simulate annihilation of defect-antidefect pair.
        
        Physical Meaning:
            Models the process where a defect and antidefect approach
            and annihilate, releasing energy and creating topological
            transitions in the field.
            
        Mathematical Foundation:
            Annihilation occurs when defects of opposite charge
            approach within a critical distance, leading to
            energy release and field relaxation.
            
        Args:
            defect_pair: Indices of defect and antidefect
            positions: Current defect positions
            charges: Current defect charges
            
        Returns:
            Dictionary containing annihilation results
        """
        i, j = defect_pair
        
        # Check if defects have opposite charges
        if charges[i] * charges[j] >= 0:
            return {"annihilated": False, "reason": "Defects have same sign charges"}
        
        # Compute separation
        r_ij = positions[j] - positions[i]
        r_magnitude = np.linalg.norm(r_ij)
        
        # Check if defects are close enough for annihilation
        annihilation_radius = self.params.get("annihilation_radius", 0.2)
        
        if r_magnitude > annihilation_radius:
            return {
                "annihilated": False,
                "reason": f"Defects too far apart: {r_magnitude:.3f} > {annihilation_radius}",
            }
        
        # Compute annihilation energy
        annihilation_energy = self.compute_annihilation_energy(
            charges[i], charges[j], r_magnitude
        )
        
        # Compute energy release rate
        energy_release_rate = self.compute_energy_release_rate(annihilation_energy)
        
        # Simulate field relaxation
        relaxation_time = self.compute_relaxation_time(r_magnitude)
        
        return {
            "annihilated": True,
            "annihilation_energy": annihilation_energy,
            "energy_release_rate": energy_release_rate,
            "relaxation_time": relaxation_time,
            "final_separation": r_magnitude,
        }

