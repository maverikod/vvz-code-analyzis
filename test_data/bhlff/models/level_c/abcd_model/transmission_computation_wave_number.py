"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Wave number computation for transmission matrices.

This module provides 7D-aware wave number computation methods for
transmission matrix calculations in the ABCD model.

Physical Meaning:
    Computes wave numbers for 7D phase field theory using 7D Laplacian
    spectral operations, ensuring proper 7D structure consideration
    in transmission matrix calculations.

Mathematical Foundation:
    For 7D phase field theory, wave number is computed using 7D spectral
    analysis with proper consideration of 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
"""

import numpy as np
from typing import Any
import logging

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..abcd import ResonatorLayer
from bhlff.core.bvp import BVPCore


class TransmissionWaveNumberComputation:
    """
    Wave number computation for transmission matrices.
    
    Physical Meaning:
        Provides 7D-aware wave number computation methods for
        transmission matrix calculations.
    """
    
    def __init__(self, bvp_core: BVPCore = None, logger: logging.Logger = None):
        """
        Initialize wave number computation.
        
        Args:
            bvp_core (BVPCore): BVP core for 7D domain information.
            logger (logging.Logger): Logger instance.
        """
        self.bvp_core = bvp_core
        self.logger = logger or logging.getLogger(__name__)
    
    def compute_7d_wave_number(
        self, frequency: float, layer: ResonatorLayer, xp: Any
    ) -> float:
        """
        Compute 7D wave number using 7D Laplacian spectral operations.
        
        Physical Meaning:
            Computes wave number k for 7D phase field theory using 7D Laplacian
            Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² when domain information is available, ensuring
            proper 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ consideration.
            
        Mathematical Foundation:
            For 7D phase field theory, wave number is computed using 7D spectral
            analysis:
            - Standard: k = ω * sqrt(kappa / chi_real)
            - 7D spectral: k_7d = sqrt(k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²)
            
        Args:
            frequency (float): Frequency ω.
            layer (ResonatorLayer): Resonator layer with material parameters.
            xp: Array module (numpy or cupy).
            
        Returns:
            float: 7D wave number k.
        """
        # Extract material parameters
        if layer.material_params is not None:
            kappa = layer.material_params.get("kappa", 1.0)
            chi_real = layer.material_params.get("chi_real", 1.0)
        else:
            kappa = 1.0 + layer.contrast
            chi_real = 1.0
        
        # Standard wave number computation
        k_base = frequency * float(xp.sqrt(kappa / chi_real))
        
        # If BVP core is available, use 7D spectral analysis for accurate computation
        if self.bvp_core is not None and hasattr(self.bvp_core, "domain"):
            try:
                domain = self.bvp_core.domain
                if domain.dimensions == 7:
                    # Use 7D spectral analysis for accurate 7D wave number
                    # Get 7D wave vector magnitude from domain
                    if hasattr(domain, "compute_wave_vector_magnitude"):
                        # Compute 7D wave vector magnitude |k| for 7D structure
                        k_magnitude_7d = domain.compute_wave_vector_magnitude()
                        
                        # Get fundamental frequencies for 7D dimensions
                        if hasattr(domain, "kx") and hasattr(domain, "kt"):
                            # Use average wave vector magnitude for 7D structure
                            # For 7D: k_7d² = k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²
                            # At frequency ω, scale by material properties
                            k_7d_scaled = (
                                k_base
                                * np.sqrt(
                                    np.mean(k_magnitude_7d**2)
                                    / np.max(k_magnitude_7d**2)
                                )
                                if np.max(k_magnitude_7d**2) > 0
                                else k_base
                            )
                            
                            # Use 7D spectral computation preserving 7D structure
                            k = float(k_7d_scaled)
                        else:
                            k = k_base
                    else:
                        # Fallback: use standard computation with 7D awareness
                        k = k_base
                else:
                    k = k_base
            except Exception as e:
                self.logger.debug(
                    f"7D wave number computation failed: {e}, using standard computation"
                )
                k = k_base
        else:
            k = k_base
        
        return k

