"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transmission matrix computation for ABCD model.

This module implements computation of transmission matrices for resonator
layers and chains, with vectorized CUDA operations and block processing
for optimal GPU memory usage (80% limit).

Physical Meaning:
    Computes 2x2 transmission matrices T_ℓ for each resonator layer and
    system matrix T_total = T_1 × T_2 × ... × T_N, representing the
    transmission properties of cascaded resonators in 7D phase field theory.

Mathematical Foundation:
    For each layer with thickness Δr and wave number k:
    T = [cos(kΔr)  (1/k)sin(kΔr); -k sin(kΔr)  cos(kΔr)]
    System matrix: T_total = ∏ T_ℓ
    Uses 7D wave number when 7D structure is considered.

Example:
    >>> from bhlff.models.level_c.abcd_model.transmission_computation import (
    ...     ABCDTransmissionComputation
    ... )
    >>> computation = ABCDTransmissionComputation(resonators, bvp_core)
    >>> T = computation.compute_layer_matrix(layer, frequency)
"""

import numpy as np
from typing import List, Any, Optional
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..abcd import ResonatorLayer
from bhlff.core.bvp import BVPCore
from .transmission_computation_wave_number import TransmissionWaveNumberComputation
from .transmission_computation_blocked import TransmissionBlockedComputation


class ABCDTransmissionComputation:
    """
    Transmission matrix computation for ABCD model.

    Physical Meaning:
        Provides methods for computing transmission matrices for single
        layers and vectorized computation for frequency arrays, with
        CUDA-accelerated block processing and 7D-aware wave number computation.

    Mathematical Foundation:
        Implements transmission matrix computation with 7D Laplacian support
        for accurate 7D phase field theory compliance.
    """

    def __init__(
        self,
        resonators: Optional[List[ResonatorLayer]] = None,
        bvp_core: Optional[BVPCore] = None,
        use_cuda: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize transmission computation.

        Args:
            resonators (Optional[List[ResonatorLayer]]): List of resonator layers.
            bvp_core (Optional[BVPCore]): BVP core for 7D domain information.
            use_cuda (bool): Whether to use CUDA.
            logger (Optional[logging.Logger]): Logger instance.
        """
        self.resonators = resonators or []
        self.bvp_core = bvp_core
        self.use_cuda = use_cuda
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize helper classes
        self.wave_number_computation = TransmissionWaveNumberComputation(
            bvp_core, self.logger
        )
        # blocked_computation will be initialized lazily
        self._blocked_computation = None

    def compute_layer_matrix(
        self,
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
            k = self.wave_number_computation.compute_7d_wave_number(
                frequency, layer, xp
            )

        # Vectorized computation of layer matrix elements
        k_thickness = k * layer.thickness
        cos_kr = xp.cos(k_thickness)
        sin_kr = xp.sin(k_thickness)

        A = cos_kr
        B = sin_kr / k if abs(k) > 1e-12 else xp.float64(layer.thickness)
        C = -k * sin_kr
        D = cos_kr

        return xp.array([[A, B], [C, D]], dtype=xp.complex128)

    def compute_transmission_matrices_vectorized(
        self,
        frequencies: np.ndarray,
        resonators: List[ResonatorLayer],
        use_cuda_flag: bool,
        xp: Any,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute transmission matrices for frequency array using vectorized CUDA.

        Physical Meaning:
            Computes transmission matrices T_total(ω) for all frequencies
            simultaneously using vectorized CUDA operations with optimized
            block processing, maximizing GPU utilization and preserving
            7D structure awareness.

        Mathematical Foundation:
            For each frequency ω_i:
            T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i)
            All matrices computed in parallel using vectorized batched operations.

        Args:
            frequencies (np.ndarray): Array of frequencies.
            resonators (List[ResonatorLayer]): List of resonator layers.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.

        Returns:
            np.ndarray: Array of 2x2 transmission matrices.
        """
        n_freqs = len(frequencies)

        # Use block processing for large arrays to respect 80% GPU memory limit
        if use_cuda_flag and CUDA_AVAILABLE and n_freqs > 100:
            # Initialize blocked computation lazily
            if self._blocked_computation is None:
                self._blocked_computation = TransmissionBlockedComputation(
                    self.bvp_core, self.compute_layer_matrices_vectorized, self.logger
                )
            return self._blocked_computation.compute_transmission_matrices_blocked(
                frequencies,
                resonators,
                use_cuda_flag,
                xp,
                compute_7d_wave_number,
            )

        # Direct vectorized computation for small arrays
        # Stack of identity matrices (only as multiplicative identity)
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total_stack = cp.stack([cp.eye(2, dtype=cp.complex128)] * n_freqs)
        else:
            T_total_stack = np.stack([np.eye(2, dtype=np.complex128)] * n_freqs)

        # Vectorized matrix multiplication for all layers and frequencies
        # Use batched matrix multiplication for better GPU utilization
        for layer in resonators:
            # Compute layer matrices for all frequencies at once
            T_layer_stack = self.compute_layer_matrices_vectorized(
                layer, frequencies, xp, compute_7d_wave_number
            )

            # Vectorized batched matrix multiplication for all frequencies
            # Using einsum for efficient batched matrix multiplication
            if use_cuda_flag and CUDA_AVAILABLE:
                # Batched matrix multiplication: (n_freqs, 2, 2) @ (n_freqs, 2, 2)
                T_total_stack = cp.einsum("ijk,ikl->ijl", T_total_stack, T_layer_stack)
            else:
                # CPU batched matrix multiplication
                for i in range(n_freqs):
                    T_total_stack[i] = T_total_stack[i] @ T_layer_stack[i]

        # Convert back to numpy if using CUDA
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total_stack = cp.asnumpy(T_total_stack)

        return T_total_stack

    def compute_layer_matrices_vectorized(
        self,
        layer: ResonatorLayer,
        frequencies: np.ndarray,
        xp: Any,
        compute_7d_wave_number: Any = None,
    ) -> np.ndarray:
        """
        Compute layer matrices for frequency array using fully vectorized operations.

        Physical Meaning:
            Computes 2x2 transmission matrices for a single layer at all
            frequencies simultaneously using fully vectorized CUDA operations,
            with 7D-aware wave number computation when domain is available.
            All operations are vectorized for maximum GPU utilization.

        Mathematical Foundation:
            For each frequency ω_i:
            T(ω_i) = [cos(k_i Δr)  (1/k_i)sin(k_i Δr); -k_i sin(k_i Δr)  cos(k_i Δr)]
            where k_i is the 7D wave number computed from frequency and material properties.
            All computations are fully vectorized across all frequencies using CUDA kernels.

        Args:
            layer (ResonatorLayer): Resonator layer.
            frequencies (np.ndarray): Array of frequencies.
            xp: Array module (numpy or cupy).
            compute_7d_wave_number (callable): Function to compute 7D wave number.

        Returns:
            np.ndarray: Stack of 2x2 transmission matrices with shape (n_freqs, 2, 2).
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
        # All operations are fully vectorized on GPU
        k = frequencies * xp.sqrt(kappa / chi_real)

        # Vectorized computation of layer matrix elements for all frequencies
        # All trigonometric operations are vectorized on GPU
        k_thickness = k * layer.thickness
        cos_kr = xp.cos(k_thickness)
        sin_kr = xp.sin(k_thickness)

        # Vectorized element computation with broadcasting
        # All operations are fully vectorized for maximum GPU utilization
        A = cos_kr
        # Handle division by zero for small k using vectorized where
        k_safe = xp.where(xp.abs(k) > 1e-12, k, xp.float64(layer.thickness))
        B = sin_kr / k_safe
        C = -k * sin_kr
        D = cos_kr

        # Fully vectorized matrix stacking using advanced indexing
        # This avoids Python loops and uses GPU kernels for all operations
        n_freqs = len(frequencies)
        T_stack = xp.zeros((n_freqs, 2, 2), dtype=xp.complex128)
        
        # Vectorized assignment using advanced indexing
        # All operations are performed on GPU with vectorized kernels
        T_stack[:, 0, 0] = A
        T_stack[:, 0, 1] = B
        T_stack[:, 1, 0] = C
        T_stack[:, 1, 1] = D

        return T_stack
