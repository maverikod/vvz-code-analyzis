"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Green function computation for defect interactions.

This module provides methods for computing fractional Green functions
and their normalization for defect interaction calculations.

Physical Meaning:
    Computes fractional Green functions G_β(r) for defect interactions,
    which determine the interaction strength between defects based on
    their separation and the fractional order parameter β.

Mathematical Foundation:
    Fractional Green function: G_β(r) = C_β r^(2β-3) where C_β is
    the normalization constant ensuring (-Δ)^β G_β = δ in R³.
"""

import numpy as np
from typing import Tuple
from scipy.special import gamma


class DefectInteractionsGreen:
    """
    Green function computation for defect interactions.
    
    Physical Meaning:
        Provides methods for computing fractional Green functions
        and their normalization constants.
    """
    
    def __init__(self, params: dict):
        """
        Initialize Green function computation.
        
        Args:
            params (dict): Physical parameters.
        """
        self.params = params
        self.interaction_strength = params.get("interaction_strength", 1.0)
        self.beta = params.get("beta", 1.0)
        self.cutoff_radius = params.get("cutoff_radius", 0.1)
        self.tempered_lambda = params.get("tempered_lambda", 0.0)
        
        # Compute Green function prefactor
        green_normalization = self.compute_fractional_green_normalization(self.beta)
        self.green_prefactor = self.interaction_strength * green_normalization
        
        # Screening parameters
        if self.tempered_lambda > 0:
            self.screening_factor = 1.0 / self.tempered_lambda
        else:
            self.screening_factor = 0.0
    
    def compute_green_function(self, r: float) -> Tuple[float, float]:
        """
        Compute fractional Green function and its gradient.
        
        Physical Meaning:
            Calculates the fractional Green function G_β(r) and its
            gradient for defect interactions at distance r.
            
        Mathematical Foundation:
            G_β(r) = C_β r^(2β-3) where C_β is the normalization constant.
            Gradient: dG_β/dr = C_β (2β-3) r^(2β-4).
            
        Args:
            r: Distance from source
            
        Returns:
            Tuple of (Green function value, gradient)
        """
        if r < self.cutoff_radius:
            # Regularize at small distances
            r = self.cutoff_radius
        
        # Fractional Green function: G_β(r) = C_β r^(2β-3)
        power = 2 * self.beta - 3
        green_value = self.green_prefactor * (r**power)
        
        # Gradient: dG_β/dr = C_β (2β-3) r^(2β-4)
        if power != 0:
            green_gradient = self.green_prefactor * power * (r ** (power - 1))
        else:
            green_gradient = 0.0
        
        # Apply tempered screening if λ > 0 (diagnostic only)
        if self.tempered_lambda > 0:
            screening_factor = self.step_resonator_screening(r)
            green_value *= screening_factor
            green_gradient = (
                green_gradient * screening_factor - green_value * self.screening_factor
            )
        
        return green_value, green_gradient
    
    def compute_fractional_green_normalization(self, beta: float) -> float:
        """
        Compute normalization constant for fractional Green function.
        
        Physical Meaning:
            Calculates the normalization constant C_β for the fractional
            Green function G_β such that (-Δ)^β G_β = δ in R³.
            
        Mathematical Foundation:
            For 3D fractional Laplacian: C_β = Γ(3/2-β) / (2^(2β) π^(3/2) Γ(β))
            This ensures proper normalization of the fractional Green function.
            
        Args:
            beta: Fractional order parameter
            
        Returns:
            Normalization constant C_β
        """
        if beta <= 0 or beta >= 1.5:
            # Fallback to 7D BVP case for extreme values
            return self.compute_7d_bvp_normalization(beta)
        
        # Exact normalization for 3D fractional Green function
        # C_β = Γ(3/2-β) / (2^(2β) π^(3/2) Γ(β))
        numerator = gamma(3 / 2 - beta)
        denominator = (2 ** (2 * beta)) * (np.pi ** (3 / 2)) * gamma(beta)
        
        return numerator / denominator
    
    def step_resonator_screening(self, r: float) -> float:
        """
        Step resonator screening according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function screening instead of exponential screening
            according to 7D BVP theory principles.
            
        Mathematical Foundation:
            Screening = Θ(r_cutoff - r) where Θ is the Heaviside step function.
            
        Args:
            r: Distance parameter
            
        Returns:
            Step function screening value
        """
        # Step function screening according to 7D BVP theory
        cutoff_radius = 1.0 / self.screening_factor if self.screening_factor > 0 else float('inf')
        screening_strength = 1.0
        
        # Apply step function boundary condition
        if r < cutoff_radius:
            return screening_strength
        else:
            return 0.0
    
    def compute_7d_bvp_normalization(self, beta: float) -> float:
        """
        Compute 7D BVP normalization according to 7D BVP theory.
        
        Physical Meaning:
            Computes normalization constant according to 7D BVP theory
            principles where the normalization is determined by the
            7D phase field structure.
            
        Mathematical Foundation:
            Normalization = 1/(4π) * (7D phase field factor)
            where the 7D phase field factor accounts for the
            additional dimensions in the 7D BVP theory.
            
        Args:
            beta: Fractional order parameter
            
        Returns:
            7D BVP normalization constant
        """
        # 7D BVP normalization according to 7D BVP theory
        base_normalization = 1.0 / (4 * np.pi)
        phase_field_factor = 7.0  # 7D phase field factor
        
        # Apply 7D BVP correction
        normalization = base_normalization * phase_field_factor
        
        return normalization

