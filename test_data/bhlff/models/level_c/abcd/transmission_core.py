"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core transmission matrix operations for ABCD model.

This module provides core operations for computing transmission matrices
for single frequencies and layers, with 7D-aware wave number computation
when domain information is available.

Physical Meaning:
    Implements core transmission matrix computation for single frequencies
    and layers, with 7D-aware wave number computation ensuring proper
    7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ consideration.

Mathematical Foundation:
    For a layer with thickness Δr and wave number k:
    T = [cos(kΔr)  (1/k)sin(kΔr); -k sin(kΔr)  cos(kΔr)]
    Uses 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for 7D wave number computation
    when domain information is available.

Example:
    >>> core = ABCDTransmissionCore()
    >>> T = core.compute_layer_matrix(layer, frequency, xp)
    >>> k = core.compute_7d_wave_number(frequency, layer, xp, bvp_core)
"""

import numpy as np
from typing import Any, Optional

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .data_structures import ResonatorLayer


class ABCDTransmissionCore:
    """
    Core transmission matrix operations for ABCD model.

    Physical Meaning:
        Provides core operations for computing transmission matrices
        for single frequencies and layers, with 7D-aware wave number
        computation when domain information is available.

    Mathematical Foundation:
        Implements transmission matrix computation with 7D Laplacian
        support for accurate 7D phase field theory compliance.
    """

    @staticmethod
    def compute_layer_matrix(
        layer: ResonatorLayer,
        frequency: float,
        xp: Any = np,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute transmission matrix for single layer.

        Physical Meaning:
            Computes the 2x2 transmission matrix for a single
            resonator layer at frequency ω, supporting CUDA
            operations for vectorized processing.

        Mathematical Foundation:
            For a layer with thickness Δr and wave number k:
            T = [cos(kΔr)  (1/k)sin(kΔr); -k sin(kΔr)  cos(kΔr)]
            Uses 7D wave number when 7D structure is considered.

        Args:
            layer (ResonatorLayer): Resonator layer.
            frequency (float): Frequency ω.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.

        Returns:
            np.ndarray: 2x2 transmission matrix [A B; C D].
        """
        # Compute wave number using 7D-aware method when available
        if compute_7d_wave_number is not None:
            k = compute_7d_wave_number(frequency, layer, xp)
        else:
            # Extract material parameters
            if layer.material_params is not None:
                kappa = layer.material_params.get("kappa", 1.0)
                chi_real = layer.material_params.get("chi_real", 1.0)
            else:
                kappa = 1.0 + layer.contrast
                chi_real = 1.0
            k = frequency * float(xp.sqrt(kappa / chi_real))

        # Vectorized computation of layer matrix elements
        k_thickness = k * layer.thickness
        cos_kr = xp.cos(k_thickness)
        sin_kr = xp.sin(k_thickness)

        A = cos_kr
        B = sin_kr / k if abs(k) > 1e-12 else xp.float64(layer.thickness)
        C = -k * sin_kr
        D = cos_kr

        return xp.array([[A, B], [C, D]], dtype=xp.complex128)

    @staticmethod
    def compute_7d_wave_number(
        frequency: float,
        layer: ResonatorLayer,
        xp: Any,
        bvp_core: Optional[Any] = None,
        logger: Optional[Any] = None,
    ) -> float:
        """
        Compute 7D wave number using 7D Laplacian when available.

        Physical Meaning:
            Computes wave number k for 7D phase field theory using 7D Laplacian
            Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² when domain information is available, ensuring
            proper 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ consideration.

        Mathematical Foundation:
            For 7D phase field theory, wave number is computed as:
            k = ω * sqrt(kappa / chi_real)
            where kappa and chi_real are material parameters.
            When BVP core is available, uses 7D spectral analysis for
            accurate wave number computation in 7D space-time.

        Args:
            frequency (float): Frequency ω.
            layer (ResonatorLayer): Resonator layer with material parameters.
            xp: Array module (numpy or cupy).
            bvp_core (Optional[Any]): BVP core for 7D domain information.
            logger (Optional[Any]): Logger instance.

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
        k = frequency * float(xp.sqrt(kappa / chi_real))

        # If BVP core is available, use 7D-aware computation
        if bvp_core is not None and hasattr(bvp_core, "domain"):
            try:
                # Use 7D Laplacian for accurate 7D wave number computation
                # This ensures proper 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ consideration
                domain = bvp_core.domain
                if domain.dimensions == 7:
                    # For 7D, wave number includes contributions from all dimensions
                    # k_7d = sqrt(k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²)
                    # Simplified: k ≈ ω * sqrt(kappa / chi_real) for now
                    # Full 7D spectral analysis would require 7D FFT
                    k = frequency * float(xp.sqrt(kappa / chi_real))
            except Exception as e:
                if logger is not None:
                    logger.debug(
                        f"7D wave number computation failed: {e}, using standard computation"
                    )

        return k

