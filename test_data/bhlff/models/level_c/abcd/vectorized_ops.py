"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized operations for ABCD transmission matrix computation.

This module provides vectorized CUDA-accelerated operations for computing
transmission matrices and admittance for frequency arrays, maximizing GPU
utilization and preserving 7D structure awareness.

Physical Meaning:
    Implements vectorized operations for parallel computation of transmission
    matrices across multiple frequencies, enabling efficient frequency sweep
    analysis with CUDA acceleration while maintaining 7D phase field theory
    compliance.

Mathematical Foundation:
    Vectorized computation of transmission matrices:
    - T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i) for all ω_i
    - All operations use vectorized CUDA kernels for maximum GPU utilization
    - Preserves 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ in wave number computation

Example:
    >>> ops = ABCDVectorizedOps()
    >>> T_stack = ops.compute_transmission_matrices_vectorized(
    ...     frequencies, layers, use_cuda_flag, xp
    ... )
"""

import numpy as np
from typing import Any, List

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .data_structures import ResonatorLayer


class ABCDVectorizedOps:
    """
    Vectorized operations for ABCD transmission matrix computation.

    Physical Meaning:
        Provides vectorized CUDA-accelerated operations for computing
        transmission matrices and admittance for frequency arrays, maximizing
        GPU utilization and preserving 7D structure awareness.

    Mathematical Foundation:
        Implements vectorized computation of transmission matrices across
        multiple frequencies using parallel CUDA operations, preserving
        7D phase field theory structure in all computations.
    """

    @staticmethod
    def compute_transmission_matrices_vectorized(
        frequencies: np.ndarray,
        layers: List[ResonatorLayer],
        use_cuda_flag: bool,
        xp: Any,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute transmission matrices for frequency array using vectorized CUDA.

        Physical Meaning:
            Computes transmission matrices T_total(ω) for all frequencies
            simultaneously using vectorized CUDA operations, maximizing
            GPU utilization and preserving 7D structure awareness.

        Mathematical Foundation:
            For each frequency ω_i:
            T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i)
            All matrices computed in parallel using vectorized operations.

        Args:
            frequencies (np.ndarray): Array of frequencies.
            layers (List[ResonatorLayer]): List of resonator layers.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.

        Returns:
            np.ndarray: Array of 2x2 transmission matrices.
        """
        n_freqs = len(frequencies)
        # Stack of identity matrices (only as multiplicative identity)
        T_total_stack = xp.stack([xp.eye(2, dtype=xp.complex128)] * n_freqs)

        # Vectorized matrix multiplication for all layers and frequencies
        for layer in layers:
            # Compute layer matrices for all frequencies at once
            T_layer_stack = ABCDVectorizedOps.compute_layer_matrices_vectorized(
                layer, frequencies, xp, compute_7d_wave_number
            )
            # Vectorized matrix multiplication: T_total @ T_layer for each frequency
            for i in range(n_freqs):
                T_total_stack[i] = T_total_stack[i] @ T_layer_stack[i]

        # Convert back to numpy if using CUDA
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total_stack = cp.asnumpy(T_total_stack)

        return T_total_stack

    @staticmethod
    def compute_layer_matrices_vectorized(
        layer: ResonatorLayer,
        frequencies: np.ndarray,
        xp: Any,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute layer matrices for frequency array using vectorized operations.

        Physical Meaning:
            Computes 2x2 transmission matrices for a single layer at all
            frequencies simultaneously using vectorized CUDA operations,
            with 7D-aware wave number computation when domain is available.

        Mathematical Foundation:
            For each frequency ω_i:
            T(ω_i) = [cos(k_i Δr)  (1/k_i)sin(k_i Δr); -k_i sin(k_i Δr)  cos(k_i Δr)]
            where k_i is the 7D wave number computed from frequency and material properties.

        Args:
            layer (ResonatorLayer): Resonator layer.
            frequencies (np.ndarray): Array of frequencies.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.

        Returns:
            np.ndarray: Stack of 2x2 transmission matrices.
        """
        # Extract material parameters
        if layer.material_params is not None:
            kappa = layer.material_params.get("kappa", 1.0)
            chi_real = layer.material_params.get("chi_real", 1.0)
            chi_imag = layer.material_params.get("chi_imag", 0.01)
        else:
            kappa = 1.0 + layer.contrast
            chi_real = 1.0
            chi_imag = 0.01 * (1.0 + layer.memory_gamma)

        # Vectorized wave number computation (7D-aware if domain available)
        # For 7D: k = ω * sqrt(kappa / chi_real) with 7D structure consideration
        if compute_7d_wave_number is not None:
            # Use 7D-aware computation for each frequency
            k = xp.array(
                [
                    compute_7d_wave_number(float(freq), layer, xp)
                    for freq in frequencies
                ]
            )
        else:
            # Standard computation
            k = frequencies * xp.sqrt(kappa / chi_real)

        # Vectorized computation of layer matrix elements for all frequencies
        k_thickness = k * layer.thickness
        cos_kr = xp.cos(k_thickness)
        sin_kr = xp.sin(k_thickness)

        # Vectorized element computation with broadcasting
        A = cos_kr
        # Handle division by zero for small k
        k_safe = xp.where(xp.abs(k) > 1e-12, k, xp.float64(layer.thickness))
        B = sin_kr / k_safe
        C = -k * sin_kr
        D = cos_kr

        # Stack matrices: shape (n_freqs, 2, 2)
        T_stack = xp.stack(
            [
                xp.array([[A[i], B[i]], [C[i], D[i]]], dtype=xp.complex128)
                for i in range(len(frequencies))
            ]
        )

        return T_stack

    @staticmethod
    def compute_admittance_vectorized(
        frequencies_gpu: np.ndarray,
        compute_transmission_matrix: Any,
        use_cuda_flag: bool,
        xp: Any,
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using vectorized operations.

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for all frequencies
            using vectorized operations, maximizing GPU utilization.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            compute_transmission_matrix (callable): Function to compute transmission matrix.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        # Compute transmission matrices for all frequencies at once
        T_stack = compute_transmission_matrix(frequencies_gpu, use_cuda=use_cuda_flag)

        # Extract A and C elements for all frequencies
        A = T_stack[:, 0, 0]
        C = T_stack[:, 1, 0]

        # Vectorized division with zero handling
        admittance = xp.where(xp.abs(A) > 1e-12, C / A, xp.complex128(0.0))

        return admittance

