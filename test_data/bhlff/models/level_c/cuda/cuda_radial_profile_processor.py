"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized radial profile processor for Level C computations.

This module provides CUDA-accelerated radial profile computation functionality
for Level C boundary analysis with automatic GPU memory management.

Physical Meaning:
    Computes radial profile A(r) = (1/4π) ∫_S(r) |a(x)|² dS for boundary
    analysis, enabling efficient spatial distribution analysis.

Mathematical Foundation:
    Implements radial profile computation:
    A(r) = (1/4π) ∫_S(r) |a(x)|² dS
    Computed for all radii simultaneously using vectorization.

Example:
    >>> processor = RadialProfileProcessor(backend, block_size, cuda_available)
    >>> profiles = processor.compute_vectorized(field, center, radii, domain)
"""

import numpy as np
from typing import Dict, Any
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .cuda_radial_profile_7d_ops import (
    compute_unblocked_cuda_7d,
    compute_blocked_cuda_7d,
)


class RadialProfileProcessor:
    """
    CUDA-optimized radial profile processor for Level C computations.

    Physical Meaning:
        Provides GPU-accelerated radial profile computation for boundary
        analysis, enabling efficient spatial distribution analysis.

    Mathematical Foundation:
        Computes radial profile A(r) = (1/4π) ∫_S(r) |a(x)|² dS.
    """

    def __init__(self, backend: Any, block_size: int, cuda_available: bool):
        """
        Initialize radial profile processor.

        Args:
            backend: CUDA or CPU backend.
            block_size (int): Block size for processing.
            cuda_available (bool): Whether CUDA is available.
        """
        self.backend = backend
        self.block_size = block_size
        self.cuda_available = cuda_available
        self.logger = logging.getLogger(__name__)

    def compute_vectorized(
        self,
        field: np.ndarray,
        center: np.ndarray,
        radii: np.ndarray,
        domain: Dict[str, Any],
    ) -> np.ndarray:
        """
        Compute 7D radial profile using GPU-accelerated vectorized operations.

        Physical Meaning:
            Computes radial profile in 7D space-time:
            A(r) = (1/Ω₆) ∫_S(r) |a(x)|² dS
            where S(r) is the 6-sphere surface at radius r in 7D space-time,
            and Ω₆ = 16π³/15 is the surface area of unit 6-sphere.
            Uses 7D radial distance: |x|² = x² + y² + z² + φ₁² + φ₂² + φ₃² + t²

        Mathematical Foundation:
            For 7D field a(x₁, x₂, x₃, φ₁, φ₂, φ₃, t), computes:
            A(r) = (1/Ω₆) ∫_{|x-x₀|=r} |a(x)|² dS
            where integration is over 6-sphere surface in 7D.

        Args:
            field (np.ndarray): 7D field data (shape: N×N×N×N_phi×N_phi×N_phi×N_t).
            center (np.ndarray): 7D center point (x, y, z, φ₁, φ₂, φ₃, t).
            radii (np.ndarray): Radii to compute profile (float64).
            domain (Dict[str, Any]): Domain parameters with 7D shape information.

        Returns:
            np.ndarray: Radial profile amplitudes for each radius (float64).

        Raises:
            RuntimeError: If CUDA is not available or backend is not CUDA.
            ValueError: If dtypes are incorrect or field is not 7D.
        """
        # CUDA is required for Level C - no CPU fallback
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - Level C requires GPU")

        # CRITICAL: Enforce precise dtypes BEFORE GPU transfer
        # Prevents dtype/object pitfalls; guarantees GPU-only execution
        if np.iscomplexobj(field):
            field = np.asarray(field, dtype=np.complex128)
        else:
            field = np.asarray(field, dtype=np.float64)

        center = np.asarray(center, dtype=np.float64).flatten()
        radii = np.asarray(radii, dtype=np.float64)

        # Verify field is 7D (theory requires 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ)
        if len(field.shape) != 7:
            raise ValueError(
                f"Field must be 7D, got shape {field.shape} "
                f"with {len(field.shape)} dimensions"
            )

        # Verify center has 7 dimensions (7D space-time)
        if len(center) != 7:
            raise ValueError(f"Center must have 7 dimensions, got {len(center)}")

        # CRITICAL: Verify no object dtypes - prevents dtype/object pitfalls
        if field.dtype == object:
            raise ValueError(
                f"field has object dtype: {field.dtype}. "
                f"Must be float64 or complex128 for GPU transfer"
            )
        if center.dtype == object:
            raise ValueError(
                f"center has object dtype: {center.dtype}. "
                f"Must be float64 for GPU transfer"
            )
        if radii.dtype == object:
            raise ValueError(
                f"radii has object dtype: {radii.dtype}. "
                f"Must be float64 for GPU transfer"
            )

        # CRITICAL: Ensure all dtypes are exactly correct before GPU transfer
        if field.dtype not in (np.float64, np.complex128):
            if np.iscomplexobj(field):
                field = field.astype(np.complex128)
            else:
                field = field.astype(np.float64)

        if center.dtype != np.float64:
            center = center.astype(np.float64)

        if radii.dtype != np.float64:
            radii = radii.astype(np.float64)

        # GPU-only execution - no CPU path
        return self._compute_cuda(field, center, domain, radii)

    def _compute_cuda(
        self,
        field: np.ndarray,
        center: np.ndarray,
        domain: Dict[str, Any],
        radii: np.ndarray,
    ) -> np.ndarray:
        """
        Compute 7D radial profile using CUDA acceleration with block processing.

        Physical Meaning:
            Computes radial profile in 7D space-time using GPU-accelerated
            block-based processing. Uses 7D radial distance computation
            with optimized memory usage (80% of GPU memory).
            Theory requires 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            For 7D field, computes distances using full 7D metric:
            |x - x₀|² = (x-x₀)² + (y-y₀)² + (z-z₀)² + (φ₁-φ₁₀)² + (φ₂-φ₂₀)² + (φ₃-φ₃₀)² + (t-t₀)²
            Uses block-based processing optimized for 80% GPU memory utilization.

        Args:
            field (np.ndarray): 7D field data (already float64/complex128).
            center (np.ndarray): 7D center point (already float64).
            domain (Dict[str, Any]): Domain parameters with 7D shape information.
            radii (np.ndarray): Radii array (already float64).

        Returns:
            np.ndarray: Radial profile amplitudes (float64).

        Raises:
            RuntimeError: If CUDA is not available or backend is not CUDA.
        """
        # CUDA is required - no CPU fallback
        if not self.cuda_available:
            raise RuntimeError("CUDA not available - Level C requires GPU")

        # CRITICAL: Verify backend is CUDA (not CPU) - guarantees GPU-only execution
        from bhlff.utils.cuda_utils import CUDABackend

        if not isinstance(self.backend, CUDABackend):
            raise RuntimeError(
                f"Backend is not CUDA! Got {type(self.backend).__name__}. "
                f"Level C requires GPU acceleration."
            )

        self.logger.info(
            f"Computing 7D radial profile on GPU: field shape={field.shape}, "
            f"num_radii={len(radii)}, field.dtype={field.dtype}, "
            f"center.dtype={center.dtype}, radii.dtype={radii.dtype}"
        )

        # CRITICAL: Transfer to GPU with explicit dtype enforcement
        # All arrays are already float64/complex128 before transfer
        # GPU sync point: ensure transfers complete before processing
        field_gpu = self.backend.array(field)
        center_gpu = self.backend.array(center)
        radii_gpu = self.backend.array(radii)

        # CRITICAL: GPU sync point after transfers
        cp.cuda.Stream.null.synchronize()

        # Verify arrays are on GPU (no CPU arrays allowed)
        if not isinstance(field_gpu, cp.ndarray):
            raise RuntimeError(
                f"Field not on GPU! Type: {type(field_gpu)}. "
                f"Level C requires GPU-only execution."
            )
        if not isinstance(center_gpu, cp.ndarray):
            raise RuntimeError(
                f"Center not on GPU! Type: {type(center_gpu)}. "
                f"Level C requires GPU-only execution."
            )
        if not isinstance(radii_gpu, cp.ndarray):
            raise RuntimeError(
                f"Radii not on GPU! Type: {type(radii_gpu)}. "
                f"Level C requires GPU-only execution."
            )

        self.logger.info(
            f"Arrays transferred to GPU: field={field_gpu.shape}, "
            f"center={center_gpu.shape}, radii={radii_gpu.shape}"
        )

        # Extract 7D shape (theory requires 7D space-time)
        shape = field.shape
        N_x, N_y, N_z, N_phi1, N_phi2, N_phi3, N_t = shape

        # Get domain parameters for 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
        L = domain.get("L", 1.0)
        L_phi = domain.get("L_phi", 2.0 * np.pi)
        L_t = domain.get("L_t", 1.0)

        # Determine if block-based processing is needed (optimized for 80% GPU memory)
        # Block size is computed to use 80% of available GPU memory
        total_elements = np.prod(shape)
        block_elements = self.block_size**7

        if total_elements > block_elements:
            # Use block-based 7D processing with optimized block size
            # GPU sync point: ensure block processing completes
            result_gpu = compute_blocked_cuda_7d(
                field_gpu, center_gpu, radii_gpu, shape, L, L_phi, L_t, self.block_size
            )
            # GPU sync point: ensure reductions complete before transfer
            cp.cuda.Stream.null.synchronize()
            result = self.backend.to_numpy(result_gpu)
        else:
            # Small field case: compute all at once on GPU (vectorized)
            result_gpu = compute_unblocked_cuda_7d(
                field_gpu, center_gpu, radii_gpu, shape, L, L_phi, L_t
            )
            # GPU sync point: ensure reductions complete before transfer
            cp.cuda.Stream.null.synchronize()
            result = self.backend.to_numpy(result_gpu)

        # CRITICAL: Ensure result is float64 (no object dtype)
        result = np.asarray(result, dtype=np.float64)
        if result.dtype == object:
            raise ValueError(
                f"Result has object dtype: {result.dtype}. "
                f"Must be float64 after GPU computation"
            )

        return result
