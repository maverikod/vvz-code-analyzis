"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU computation of electroweak currents for 7D blocks.

This module implements GPU-accelerated computation of electroweak currents
for 7D blocks with vectorized operations and explicit memory management.

Physical Meaning:
    Computes electroweak currents for a single 7D block using strict GPU
    path with vectorized operations. All operations preserve 7D structure
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with explicit memory management.

Mathematical Foundation:
    All operations preserve 7D structure:
    - Gradients computed in all 7 dimensions (axes 0-6)
    - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
    - Currents computed with vectorized GPU operations
    - Explicit memory accounting prevents OOM errors

Example:
    >>> from bhlff.core.bvp.phase_vector.electroweak_gpu_computation import ElectroweakGPUComputation
    >>> gpu_compute = ElectroweakGPUComputation(coefficients)
    >>> currents = gpu_compute.compute_block_currents_gpu(envelope_block, phase_blocks, block_shape)
"""

import numpy as np
from typing import Dict, List, Tuple
import logging

# CUDA optimization - strict GPU path only
try:
    import cupy as cp

    CUDA_AVAILABLE = True
    logging.info("CUDA support enabled with CuPy")
except ImportError:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore
    logging.warning(
        "CUDA not available for electroweak coupling computation. "
        "Some features may be limited. Install cupy to enable GPU acceleration."
    )


class ElectroweakGPUComputation:
    """
    GPU computation of electroweak currents for 7D blocks.

    Physical Meaning:
        Computes electroweak currents for a single 7D block using strict GPU
        path with vectorized operations. All operations preserve 7D structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with explicit memory management.

    Mathematical Foundation:
        All operations preserve 7D structure:
        - Gradients computed in all 7 dimensions (axes 0-6)
        - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
        - Currents computed with vectorized GPU operations
        - Explicit memory accounting prevents OOM errors

    Attributes:
        electroweak_coefficients (Dict[str, float]): Electroweak coupling coefficients.
        logger (logging.Logger): Logger instance.
    """

    def __init__(self, electroweak_coefficients: Dict[str, float]) -> None:
        """
        Initialize GPU computation module.

        Physical Meaning:
            Sets up the GPU computation module with electroweak coupling
            coefficients for computing currents in 7D blocks.

        Args:
            electroweak_coefficients (Dict[str, float]): Electroweak coupling coefficients
                including em_coupling, weak_coupling, mixing_angle, gauge_coupling.
        """
        self.electroweak_coefficients = electroweak_coefficients
        self.logger = logging.getLogger(__name__)

        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

    def compute_block_currents_gpu(
        self,
        envelope_block: np.ndarray,
        phase_blocks: List[np.ndarray],
        block_shape: Tuple[int, ...],
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents for a 7D block on GPU with vectorization.

        Physical Meaning:
            Computes electroweak currents for a single 7D block using strict GPU
            path with vectorized operations. All operations preserve 7D structure
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with explicit memory management.

        Mathematical Foundation:
            All operations preserve 7D structure:
            - Gradients computed in all 7 dimensions (axes 0-6)
            - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
            - Currents computed with vectorized GPU operations
            - Explicit memory accounting prevents OOM errors

        Args:
            envelope_block: Envelope block (7D numpy array, will be transferred to GPU).
            phase_blocks: Phase component blocks (list of 7D numpy arrays).
            block_shape: Shape of the 7D block.

        Returns:
            Dict[str, np.ndarray]: Currents for this 7D block (CPU arrays).

        Raises:
            RuntimeError: If CUDA is not available or block processing fails.
            ValueError: If blocks are not 7D or shapes don't match.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute block currents on GPU")

        # Verify 7D structure
        if envelope_block.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block, got {envelope_block.ndim}D. "
                f"Shape: {envelope_block.shape}"
            )

        if envelope_block.shape != block_shape:
            raise ValueError(
                f"Envelope block shape {envelope_block.shape} doesn't match "
                f"expected block shape {block_shape}"
            )

        for i, pb in enumerate(phase_blocks):
            if pb.ndim != 7:
                raise ValueError(
                    f"Expected 7D phase block {i}, got {pb.ndim}D. Shape: {pb.shape}"
                )
            if pb.shape != block_shape:
                raise ValueError(
                    f"Phase block {i} shape {pb.shape} doesn't match "
                    f"expected block shape {block_shape}"
                )

        # Create CUDA stream for parallel operations and memory management
        stream = cp.cuda.Stream()
        stream.use()

        # Transfer all blocks to GPU - strict GPU path with async transfer
        envelope_gpu = cp.asarray(envelope_block, dtype=cp.complex128)
        phase_blocks_gpu = [
            cp.asarray(theta_a, dtype=cp.complex128) for theta_a in phase_blocks
        ]
        stream.synchronize()

        # Compute phase gradients in all 7 dimensions for 7D space-time
        # All gradients computed with vectorized GPU operations using CUDA stream
        phase_gradients = []
        for theta_a_gpu in phase_blocks_gpu:
            # Compute gradients in all 7 dimensions: ℝ³ₓ (0,1,2), 𝕋³_φ (3,4,5), ℝₜ (6)
            # Use vectorized gradient computation for all axes simultaneously
            gradients = [
                cp.gradient(theta_a_gpu, axis=0),  # x
                cp.gradient(theta_a_gpu, axis=1),  # y
                cp.gradient(theta_a_gpu, axis=2),  # z
                cp.gradient(theta_a_gpu, axis=3),  # φ₁
                cp.gradient(theta_a_gpu, axis=4),  # φ₂
                cp.gradient(theta_a_gpu, axis=5),  # φ₃
                cp.gradient(theta_a_gpu, axis=6),  # t
            ]
            stream.synchronize()

            # Compute magnitude of gradient vector in 7D using fully vectorized operations
            # |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
            # Optimized: compute all squares in one pass, then sum and sqrt
            grad_squares = cp.zeros_like(theta_a_gpu, dtype=cp.complex128)
            for g in gradients:
                grad_squares += g * cp.conj(g)  # Vectorized: |g|² = g * conj(g) for complex
            
            grad_theta = cp.sqrt(cp.real(grad_squares))  # Real magnitude from complex squared
            phase_gradients.append(grad_theta)

            # Cleanup intermediate gradients with explicit memory management
            del gradients, grad_squares
            cp.get_default_memory_pool().free_all_blocks()
            stream.synchronize()

        # Compute currents on GPU with fully vectorized operations
        # All operations preserve 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
        em_gradient = phase_gradients[0]
        weak_gradient = phase_gradients[1] + phase_gradients[2]  # Vectorized sum
        mixing_angle = self.electroweak_coefficients["mixing_angle"]

        # Pre-compute envelope powers for vectorized operations
        # Use in-place operations where possible to reduce memory usage
        envelope_squared = envelope_gpu ** 2
        envelope_power4 = envelope_squared ** 2  # More efficient than envelope_gpu ** 4
        envelope_power3 = envelope_squared * envelope_gpu  # More efficient than envelope_gpu ** 3
        stream.synchronize()

        # Vectorized current computations with explicit stream synchronization
        em_coupling = self.electroweak_coefficients["em_coupling"]
        weak_coupling = self.electroweak_coefficients["weak_coupling"]
        gauge_coupling = self.electroweak_coefficients["gauge_coupling"]
        
        em_current_gpu = em_coupling * envelope_squared * em_gradient
        weak_current_gpu = weak_coupling * envelope_power4 * weak_gradient
        
        # Pre-compute mixing factors for vectorized operations
        mixing_cos = cp.cos(mixing_angle)
        mixing_sin = cp.sin(mixing_angle)
        mixed_gradient = mixing_cos * em_gradient + mixing_sin * weak_gradient
        mixed_current_gpu = gauge_coupling * envelope_power3 * mixed_gradient
        stream.synchronize()

        # Transfer results to CPU
        result = {
            "em_current": cp.asnumpy(em_current_gpu),
            "weak_current": cp.asnumpy(weak_current_gpu),
            "mixed_current": cp.asnumpy(mixed_current_gpu),
        }

        # Cleanup GPU memory - explicit deletion of all intermediate arrays
        del em_current_gpu, weak_current_gpu, mixed_current_gpu
        del envelope_gpu, envelope_squared, envelope_power4, envelope_power3
        del em_gradient, weak_gradient, mixing_cos, mixing_sin
        del phase_blocks_gpu
        for grad in phase_gradients:
            del grad
        cp.get_default_memory_pool().free_all_blocks()

        return result

