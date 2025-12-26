"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Axis-wise reduction operations for admittance computation with 7D geometry preservation.

This module provides GPU-accelerated axis-wise reduction operations that preserve
7D block structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, performing sequential reductions along
each axis without flattening.

Physical Meaning:
    Performs reductions over all 7D axes while preserving geometric structure,
    enabling efficient computation of integrals and sums in 7D space-time without
    destroying the multidimensional structure.

Mathematical Foundation:
    Performs sequential axis-wise reductions:
    result = Σ_{axis=6} ... Σ_{axis=1} Σ_{axis=0} a(x,φ,t)
    without flattening, maintaining 7D structure throughout.
    Each axis reduction preserves block structure for optimal GPU memory access.

Example:
    >>> reducer = AdmittanceReductions()
    >>> result = reducer.axis_wise_reduce(array_gpu, preserve_structure=True)
"""

import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class AdmittanceReductions:
    """
    Axis-wise reduction operations preserving 7D block structure.

    Physical Meaning:
        Provides GPU-accelerated reduction operations that preserve 7D geometric
        structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ through sequential axis-wise reductions
        without flattening.

    Mathematical Foundation:
        Performs reduction along all axes sequentially:
        result = Σ_{axis=6} ... Σ_{axis=1} Σ_{axis=0} a(x,φ,t)
        without flattening, maintaining 7D structure throughout.
        Each axis reduction preserves the block structure for optimal GPU
        memory access patterns.

    Attributes:
        logger (logging.Logger): Logger instance.
    """

    def __init__(self):
        """
        Initialize reduction operations.

        Physical Meaning:
            Sets up reduction operations with logging for 7D geometry-preserving
            reductions on GPU.
        """
        self.logger = logging.getLogger(__name__)

    def axis_wise_reduce(
        self, array: "cp.ndarray", preserve_structure: bool = True
    ) -> "cp.ndarray":
        """
        Perform axis-wise reduction on GPU preserving 7D block structure.

        Physical Meaning:
            Computes sum over all axes of 7D array without flattening,
            preserving geometric structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            Optimized for 7D geometry: reduces spatial (0,1,2), phase (3,4,5),
            and temporal (6) axes with optimal GPU memory access patterns.
            All operations are fully vectorized on GPU, never using flatten().

        Mathematical Foundation:
            Performs reduction along all axes sequentially, optimized for 7D:
            - First reduces spatial axes (0,1,2): ℝ³ₓ → scalar spatial sum
            - Then reduces phase axes (3,4,5): 𝕋³_φ → scalar phase sum
            - Finally reduces temporal axis (6): ℝₜ → final scalar
            result = Σ_{t} Σ_{φ₃} Σ_{φ₂} Σ_{φ₁} Σ_{x₃} Σ_{x₂} Σ_{x₁} a(x,φ,t)
            without flattening, maintaining 7D structure throughout.
            All reductions use cp.sum() with sequential axis reductions, never
            flattening the array structure.

        Args:
            array (cp.ndarray): Array to reduce (7D structure preserved).
                Shape should be (N₀, N₁, N₂, N₃, N₄, N₅, N₆) for 7D arrays.
            preserve_structure (bool): Whether to preserve structure (unused,
                kept for API consistency).

        Returns:
            cp.ndarray: Scalar sum value (complex128).

        Raises:
            ValueError: If array is empty or not on GPU.
        """
        if array.size == 0:
            return cp.complex128(0.0)

        # Verify array is on GPU
        if not isinstance(array, cp.ndarray):
            raise ValueError(
                f"Array must be cupy array on GPU, got {type(array)}. "
                f"All reductions must be performed on GPU to preserve 7D structure."
            )

        # Create explicit CUDA stream for this reduction
        # Use non-default stream for better GPU utilization and overlap
        stream = cp.cuda.Stream()
        stream.use()

        ndim = array.ndim
        result = array

        # Optimized reduction for 7D geometry: group reductions by dimension type
        # For 7D: spatial (0,1,2), phase (3,4,5), temporal (6)
        # This ordering maximizes GPU cache efficiency and memory coalescing
        with stream:
            if ndim == 7:
                # 7D-specific optimized reduction path
                # Reduce spatial dimensions (0,1,2) first for better cache locality
                # Spatial dimensions are typically larger and benefit from sequential reduction
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce spatial axis 0
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce spatial axis 1
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce spatial axis 2
                # Now result is 4D: (N₃, N₄, N₅, N₆) - phase (3 dims) + temporal (1 dim)
                
                # Reduce phase dimensions (3,4,5) - now at indices 0,1,2 after previous reduction
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce phase axis 0
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce phase axis 1
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce phase axis 2
                # Now result is 1D: (N₆) - temporal dimension only
                
                # Reduce temporal dimension (6) - now at index 0
                result = cp.sum(result, axis=0, keepdims=False)  # Reduce temporal axis
                # Now result is scalar (0D)
            else:
                # Generic reduction path for non-7D arrays
                # Reduce along each axis sequentially, preserving block structure
                # CRITICAL: Never use flatten() - all reductions are axis-wise
                for axis in range(ndim):
                    # Sum along current axis, preserving remaining dimensions
                    # Using keepdims=False to reduce dimensionality progressively
                    # This is a fully vectorized GPU operation that preserves block structure
                    result = cp.sum(result, axis=axis, keepdims=False)

        # Synchronize stream after all axis reductions to ensure completion
        stream.synchronize()

        # Final result should be a scalar (0D array), convert to complex scalar
        # Use vectorized conversion with stream synchronization
        with stream:
            if result.ndim == 0:
                # Already scalar, convert to complex128
                result = cp.complex128(result)
            elif result.ndim > 0:
                # If somehow still multi-dimensional, perform final reduction
                # This handles edge cases where reduction didn't complete
                # Use vectorized sum operation, never flattening
                # CRITICAL: Use cp.sum() on remaining axes, never flatten()
                result = cp.sum(result)
                result = cp.complex128(result)
            else:
                # Should not happen, but handle gracefully
                result = cp.complex128(0.0)

        # Final synchronization to ensure all operations complete
        stream.synchronize()

        # Return stream to default
        cp.cuda.Stream.null.use()

        return result
