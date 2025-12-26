"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for domain effects analyzer.

This module provides helper methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class DomainEffectsAnalyzerHelpersMixin:
    """Mixin providing helper methods."""
    
    def _compute_domain_size_effects(
        self, solution: np.ndarray, x: np.ndarray, L: float, N: int
    ) -> Dict[str, Any]:
        """Compute domain size effects on the solution."""
        try:
            # Compute boundary effects
            boundary_region = int(N * 0.1)  # 10% of domain near boundaries
            interior_region = (
                solution[boundary_region:-boundary_region]
                if boundary_region > 0
                else solution
            )
            
            # Compute boundary vs interior statistics
            boundary_intensity = (
                np.mean(np.abs(solution[:boundary_region]))
                if boundary_region > 0
                else 0.0
            )
            interior_intensity = (
                np.mean(np.abs(interior_region)) if len(interior_region) > 0 else 0.0
            )
            
            # Compute domain size scaling
            domain_scaling = L / N  # Grid spacing
            
            return {
                "boundary_intensity": float(boundary_intensity),
                "interior_intensity": float(interior_intensity),
                "boundary_effect_ratio": float(
                    boundary_intensity / max(interior_intensity, 1e-10)
                ),
                "domain_scaling": float(domain_scaling),
                "grid_resolution": N,
                "domain_size": L,
            }
        
        except Exception as e:
            return {
                "boundary_intensity": 0.0,
                "interior_intensity": 0.0,
                "boundary_effect_ratio": 0.0,
                "domain_scaling": L / N,
                "grid_resolution": N,
                "domain_size": L,
            }
    
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

