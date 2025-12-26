"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transmission matrix computation methods for ABCD model.

This module provides transmission matrix computation methods as a mixin class.
"""

import numpy as np
from typing import Union, Optional

# Try to import CUDA
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..admittance_computation import ABCDAdmittanceComputation


class ABCDModelTransmissionMixin:
    """Mixin providing transmission matrix computation methods."""
    
    def compute_transmission_matrix(
        self,
        frequency: Union[float, np.ndarray],
        use_cuda: Optional[bool] = None,
    ) -> Union[np.ndarray, np.ndarray]:
        """
        Compute 2x2 transmission matrix for given frequency or frequency array.
        
        Physical Meaning:
            Computes the overall transmission matrix T_total(ω) for the
            entire resonator chain at frequency ω, representing the
            system's transmission properties. Uses np.eye(2) only as
            multiplicative identity for 2×2 ABCD matrix operations.
            Supports vectorized computation for frequency arrays with CUDA
            and 7D Laplacian-aware wave number computation with optimized
            block processing for 80% GPU memory usage.
            
        Mathematical Foundation:
            T_total = T_1 × T_2 × ... × T_N
            where each T_ℓ is computed from layer properties using 7D wave number
            k_7d = sqrt(k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²)
            when 7D domain is available. Identity matrix np.eye(2) is used only
            as initial value for matrix multiplication, not as a generic criterion.
            For frequency arrays, computes matrices for all frequencies using
            vectorized CUDA operations with 7D-aware block processing (80% GPU memory).
            Uses 7D block tiling from CUDABackend7DOps for optimal batch size calculation.
            
        Args:
            frequency (Union[float, np.ndarray]): Frequency ω or array of frequencies.
            use_cuda (Optional[bool]): Override CUDA usage flag.
            
        Returns:
            Union[np.ndarray, np.ndarray]: 2x2 transmission matrix [A B; C D]
                or array of matrices if frequency is array.
        """
        if not self.resonators:
            # Return identity matrix only as multiplicative identity
            if isinstance(frequency, np.ndarray):
                # Return array of identity matrices for vectorized case
                n_freqs = len(frequency)
                if use_cuda is not None and use_cuda and CUDA_AVAILABLE:
                    return cp.stack([cp.eye(2, dtype=cp.complex128)] * n_freqs)
                return np.stack([np.eye(2, dtype=np.complex128)] * n_freqs)
            return np.eye(2, dtype=np.complex128)
        
        # Initialize admittance computation if not already done
        if self._admittance_computation is None:
            self._admittance_computation = ABCDAdmittanceComputation(
                self.compute_transmission_matrix, self.logger
            )
        
        # Use CUDA if available and requested
        use_cuda_flag = (
            use_cuda if use_cuda is not None else (self.use_cuda and CUDA_AVAILABLE)
        )
        xp = cp if use_cuda_flag else np
        
        # Handle vectorized frequency array case with optimized block processing
        if isinstance(frequency, np.ndarray):
            n_freqs = len(frequency)
            # Use block processing for arrays to respect 80% GPU memory limit
            # Use 7D block tiling for optimal batch size when available
            if use_cuda_flag and CUDA_AVAILABLE and n_freqs > 50:
                return (
                    self._transmission_computation.compute_transmission_matrices_blocked(
                        frequency,
                        self.resonators,
                        use_cuda_flag,
                        xp,
                        self._compute_7d_wave_number,
                    )
                )
            else:
                return (
                    self._transmission_computation.compute_transmission_matrices_vectorized(
                        frequency,
                        self.resonators,
                        use_cuda_flag,
                        xp,
                        self._compute_7d_wave_number,
                    )
                )
        
        # Single frequency case
        # Start with identity matrix (only as multiplicative identity)
        T_total = xp.eye(2, dtype=xp.complex128)
        
        # Vectorized matrix multiplication for all layers
        # Multiply by each layer matrix with 7D-aware wave number computation
        for layer in self.resonators:
            T_layer = self._transmission_computation.compute_layer_matrix(
                layer, float(frequency), xp, self._compute_7d_wave_number
            )
            T_total = T_total @ T_layer
        
        # Convert back to numpy if using CUDA
        if use_cuda_flag and CUDA_AVAILABLE:
            T_total = cp.asnumpy(T_total)
        
        return T_total

