"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU block processing for electroweak coupling computations.

This module implements GPU-accelerated block processing for electroweak
coupling computations with 7D space-time structure preservation.

Physical Meaning:
    Processes 7D blocks on GPU with vectorized operations, computing
    electroweak currents for each block while preserving 7D geometric
    structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    All operations preserve 7D structure:
    - Gradients computed in all 7 dimensions (axes 0-6)
    - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
    - Currents computed with vectorized GPU operations

Example:
    >>> processor = ElectroweakBlockProcessor(coefficients)
    >>> currents = processor.compute_block_currents(envelope_block, phase_blocks, domain, tiling)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.domain import Domain

# CUDA optimization - GPU path when available
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


class ElectroweakBlockProcessor:
    """
    GPU block processor for electroweak coupling computations.

    Physical Meaning:
        Processes 7D blocks on GPU with vectorized operations, computing
        electroweak currents for each block while preserving 7D geometric
        structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        All operations preserve 7D structure:
        - Gradients computed in all 7 dimensions (axes 0-6)
        - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
        - Currents computed with vectorized GPU operations

    Attributes:
        electroweak_coefficients (Dict[str, float]): Electroweak coupling coefficients.
        logger (logging.Logger): Logger instance.
    """

    def __init__(self, electroweak_coefficients: Dict[str, float]) -> None:
        """
        Initialize block processor.

        Physical Meaning:
            Sets up the processor with electroweak coupling coefficients
            for computing currents in 7D blocks.

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

    def compute_block_currents(
        self,
        envelope_block: np.ndarray,
        phase_blocks: List[np.ndarray],
        domain: Domain,
        optimal_7d_tiling: Tuple[int, ...],
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents for a single 7D block on GPU with vectorization.

        Physical Meaning:
            Computes electroweak currents for a single 7D block using GPU acceleration
            with vectorized operations. Block size is already optimized to fit in 80%
            of GPU memory using 7D block tiling.

        Mathematical Foundation:
            All operations preserve 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Gradients computed in all 7 dimensions (axes 0-6)
            - Gradient magnitude: |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
            - Currents computed with vectorized GPU operations

        Args:
            envelope_block: Envelope block (7D, already sized for GPU).
            phase_blocks: Phase component blocks (7D, already sized for GPU).
            domain: Domain with 7D shape.
            optimal_7d_tiling: Optimal 7D block tiling (7-tuple).

        Returns:
            Dict[str, np.ndarray]: Currents for this 7D block (CPU arrays).

        Raises:
            RuntimeError: If CUDA is not available or block processing fails.
            ValueError: If blocks are not 7D.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute block currents")

        # Verify 7D structure
        if envelope_block.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block, got {envelope_block.ndim}D. "
                f"Shape: {envelope_block.shape}"
            )

        for i, pb in enumerate(phase_blocks):
            if pb.ndim != 7:
                raise ValueError(
                    f"Expected 7D phase block {i}, got {pb.ndim}D. Shape: {pb.shape}"
                )

        # Transfer all blocks to GPU - strict GPU path
        envelope_gpu = cp.asarray(envelope_block)
        phase_blocks_gpu = [cp.asarray(theta_a) for theta_a in phase_blocks]

        # Compute phase gradients in all 7 dimensions for 7D space-time
        # All gradients computed with vectorized GPU operations
        phase_gradients = []
        for theta_a_gpu in phase_blocks_gpu:
            # Compute gradients in all 7 dimensions: ℝ³ₓ (0,1,2), 𝕋³_φ (3,4,5), ℝₜ (6)
            gradients = [
                self._cuda_gradient_7d(theta_a_gpu, axis=0),  # x
                self._cuda_gradient_7d(theta_a_gpu, axis=1),  # y
                self._cuda_gradient_7d(theta_a_gpu, axis=2),  # z
                self._cuda_gradient_7d(theta_a_gpu, axis=3),  # φ₁
                self._cuda_gradient_7d(theta_a_gpu, axis=4),  # φ₂
                self._cuda_gradient_7d(theta_a_gpu, axis=5),  # φ₃
                self._cuda_gradient_7d(theta_a_gpu, axis=6),  # t
            ]

            # Compute magnitude of gradient vector in 7D using vectorized operations
            # |∇Θ| = sqrt(Σᵢ (∂Θ/∂xᵢ)²) for i = 0..6
            grad_squares = [g ** 2 for g in gradients]  # Vectorized squaring
            grad_theta = cp.sqrt(sum(grad_squares))  # Vectorized sum and sqrt
            phase_gradients.append(grad_theta)

            # Cleanup intermediate gradients with explicit memory management
            del gradients, grad_squares
            cp.get_default_memory_pool().free_all_blocks()

        # Compute currents on GPU with vectorized operations
        # All operations preserve 7D structure
        em_gradient = phase_gradients[0]
        weak_gradient = phase_gradients[1] + phase_gradients[2]  # Vectorized sum
        mixing_angle = self.electroweak_coefficients["mixing_angle"]

        # Vectorized current computations
        envelope_squared = envelope_gpu ** 2
        envelope_power4 = envelope_gpu ** 4
        envelope_power3 = envelope_gpu ** 3

        em_current_gpu = (
            self.electroweak_coefficients["em_coupling"] * envelope_squared * em_gradient
        )
        weak_current_gpu = (
            self.electroweak_coefficients["weak_coupling"]
            * envelope_power4
            * weak_gradient
        )

        mixing_cos = cp.cos(mixing_angle)
        mixing_sin = cp.sin(mixing_angle)
        mixed_current_gpu = (
            self.electroweak_coefficients["gauge_coupling"]
            * envelope_power3
            * (mixing_cos * em_gradient + mixing_sin * weak_gradient)
        )

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

    def _cuda_gradient_7d(self, array: "cp.ndarray", axis: int = 0) -> "cp.ndarray":
        """
        Compute gradient in 7D space-time using CUDA with vectorization.

        Physical Meaning:
            Computes gradient along specified axis in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            using CUDA for optimal performance with vectorized operations.

        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Computes gradient along axis using central differences
            - Preserves 7D structure throughout computation
            - Optimized for GPU memory access patterns

        Args:
            array (cp.ndarray): Input 7D array on GPU.
            axis (int): Axis along which to compute gradient (0-6 for 7D).

        Returns:
            cp.ndarray: Gradient array in 7D space-time.

        Raises:
            ValueError: If array is not 7D or axis is out of range.
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute 7D gradient")

        if array.ndim != 7:
            raise ValueError(
                f"Expected 7D array for gradient computation, "
                f"got {array.ndim}D. Shape: {array.shape}"
            )

        if axis < 0 or axis >= 7:
            raise ValueError(
                f"Axis must be in range [0, 6] for 7D array, got {axis}"
            )

        # Compute gradient using CUDA with vectorization
        # cp.gradient handles 7D arrays efficiently with proper memory access
        return cp.gradient(array, axis=axis)

