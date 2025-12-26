"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D operations for BVP CUDA block processing.

This module implements 7D-specific operations for BVP CUDA block processing,
including 7D Laplacian computation and optimal block tiling calculation.

Physical Meaning:
    Provides 7D operations for BVP CUDA block processing, including
    7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² computation and optimal block tiling
    for 80% GPU memory usage in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Implements 7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
    - Block tiling: optimized for 80% GPU memory usage
    - BVP solving: ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)

Example:
    >>> ops = BVPCuda7DOperations(domain, config, _7d_ops)
    >>> laplacian = ops.compute_7d_laplacian_vectorized(field, h=1.0)
    >>> block_tiling = ops.compute_optimal_block_tiling_7d(field_shape)
"""

import numpy as np
from typing import Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    try:
        import cupy as cp
    except ImportError:
        cp = None
else:
    try:
        import cupy as cp
    except ImportError:
        cp = None

from ....domain import Domain
from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps


class BVPCuda7DOperations:
    """
    7D operations for BVP CUDA block processing.

    Physical Meaning:
        Provides 7D-specific operations for BVP CUDA block processing,
        including 7D Laplacian computation and optimal block tiling
        for GPU memory optimization.

    Mathematical Foundation:
        Implements 7D operations preserving structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - Block tiling: optimized for 80% GPU memory usage
    """

    def __init__(
        self,
        domain: Domain,
        config: dict,
        _7d_ops: Optional[CUDABackend7DOps],
        block_size: int,
    ):
        """
        Initialize 7D operations for BVP CUDA block processing.

        Physical Meaning:
            Sets up 7D operations system for BVP CUDA block processing
            with GPU memory optimization.

        Args:
            domain (Domain): 7D computational domain.
            config (dict): BVP configuration parameters.
            _7d_ops (Optional[CUDABackend7DOps]): 7D operations backend.
            block_size (int): Default block size.
        """
        self.domain = domain
        self.config = config
        self._7d_ops = _7d_ops
        self.block_size = block_size

        # Extract BVP parameters
        env_eq = config.get("envelope_equation", {})
        self.kappa_0 = cp.float32(env_eq.get("kappa_0", 1.0)) if cp else None
        self.kappa_2 = cp.float32(env_eq.get("kappa_2", 0.1)) if cp else None
        self.chi_prime = cp.float32(env_eq.get("chi_prime", 1.0)) if cp else None
        self.chi_double_prime_0 = (
            cp.float32(env_eq.get("chi_double_prime_0", 0.1)) if cp else None
        )
        self.k0 = cp.float32(env_eq.get("k0", 1.0)) if cp else None

    def compute_7d_laplacian_vectorized(
        self, field: "cp.ndarray", h: float
    ) -> "cp.ndarray":
        """
        Compute 7D Laplacian using fully vectorized CUDA operations.

        Physical Meaning:
            Computes 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² using fully vectorized
            GPU operations for optimal performance in 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            For 7D field a(x,φ,t) with grid spacing h:
            Δ₇ a ≈ Σᵢ₌₀⁶ (a(x+h·eᵢ) - 2a(x) + a(x-h·eᵢ)) / h²
            where eᵢ are unit vectors in each of the 7 dimensions.
            All operations are vectorized on GPU for maximum efficiency.

        Args:
            field (cp.ndarray): 7D field on GPU with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            h (float): Grid spacing.

        Returns:
            cp.ndarray: 7D Laplacian result on GPU with same shape.

        Raises:
            ValueError: If field is not 7D.
        """
        if field.ndim != 7:
            raise ValueError(
                f"Expected 7D field for 7D Laplacian, got {field.ndim}D. "
                f"Shape: {field.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        h_sq = h * h
        # Initialize Laplacian with vectorized zero array
        lap = cp.zeros_like(field, dtype=cp.complex128)

        # Vectorized computation over all 7 dimensions
        # All operations are performed on GPU with vectorized kernels
        # Using explicit vectorized operations for optimal performance
        for axis in range(7):
            # Vectorized roll operations on GPU (efficient memory access)
            field_plus = cp.roll(field, 1, axis=axis)
            field_minus = cp.roll(field, -1, axis=axis)
            # Vectorized Laplacian computation for this dimension
            # All operations are vectorized on GPU for maximum efficiency
            lap += (field_plus - 2.0 * field + field_minus) / h_sq

        # Synchronize to ensure computation completes
        cp.cuda.Stream.null.synchronize()
        return lap

    def compute_optimal_block_tiling_7d(
        self, field_shape: Tuple[int, ...], memory_fraction: float = 0.8
    ) -> Tuple[int, ...]:
        """
        Compute optimal 7D block tiling for specified GPU memory usage.

        Physical Meaning:
            Calculates optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring specified fraction of GPU memory
            usage while preserving 7D geometric structure with optimal
            memory access patterns for vectorized operations.

        Mathematical Foundation:
            For 7D array with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - Available memory: memory_fraction × free GPU memory
            - Block size per dimension: (available_memory / overhead) ^ (1/7)
            - Optimizes for 7D geometry: spatial (0,1,2), phase (3,4,5),
              temporal (6) with vectorized GPU operations

        Args:
            field_shape (Tuple[int, ...]): Shape of 7D field array.
            memory_fraction (float): Fraction of free GPU memory to use
                (default: 0.8 for 80% usage).

        Returns:
            Tuple[int, ...]: Optimal block tiling per dimension (7-tuple),
                ensuring each dimension has block size that fits in specified
                GPU memory fraction with vectorized operations.

        Raises:
            ValueError: If field_shape is not 7D.
            RuntimeError: If GPU memory calculation fails.
        """
        if len(field_shape) != 7:
            raise ValueError(
                f"Expected 7D field shape for optimal 7D block tiling, "
                f"got {len(field_shape)}D. Shape: {field_shape}"
            )

        if self._7d_ops is not None:
            # Use optimized 7D block tiling from CUDABackend7DOps
            return self._7d_ops.compute_optimal_block_tiling_7d(
                field_shape,
                dtype=np.complex128,
                memory_fraction=memory_fraction,
                overhead_factor=10.0,  # For complex 7D BVP operations
            )
        else:
            # Fallback: compute manually if _7d_ops not available
            if cp is None:
                return tuple([self.block_size] * 7)

            try:
                # Get GPU memory info
                mem_info = cp.cuda.runtime.memGetInfo()
                free_memory_bytes = mem_info[0]

                # Use specified fraction of free memory
                available_memory_bytes = int(free_memory_bytes * memory_fraction)

                # Memory per element (complex128 = 16 bytes)
                bytes_per_element = 16

                # For 7D BVP operations, we need space for:
                # - Input field: 1x
                # - Source field: 1x
                # - Laplacian computation: 1x (7D gradients)
                # - Nonlinear terms: 2x (stiffness, susceptibility)
                # - Intermediate operations: 2x
                # - Output arrays: 1x
                # Total overhead: ~8x for 7D BVP operations
                overhead_factor = 8.0

                # Maximum elements per 7D block
                max_elements_per_block = available_memory_bytes // (
                    bytes_per_element * overhead_factor
                )

                # For 7D, calculate block size per dimension
                elements_per_dim = int(max_elements_per_block ** (1.0 / 7.0))

                # Ensure minimum block size for robust 7D operations
                min_block_size = 4
                max_block_size = min(field_shape)  # Don't exceed field dimensions

                # Clamp block size to reasonable bounds
                block_size_per_dim = max(
                    min_block_size, min(elements_per_dim, max_block_size)
                )

                # Create 7-tuple with same block size per dimension
                block_tiling = tuple([block_size_per_dim] * 7)

                return block_tiling

            except Exception as e:
                # Fallback to default block size if calculation fails
                return tuple([self.block_size] * 7)

    def solve_block_bvp_cuda_7d(
        self,
        current_block: "cp.ndarray",
        source_block: "cp.ndarray",
        block_info,
    ) -> "cp.ndarray":
        """
        Solve BVP equation for a single block using CUDA with 7D Laplacian.

        Physical Meaning:
            Solves the 7D BVP envelope equation for a single block using
            CUDA-accelerated operations with proper 7D Laplacian
            Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            All operations are fully vectorized for optimal GPU performance.

        Mathematical Foundation:
            Solves ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) using 7D Laplacian
            with fully vectorized GPU operations for optimal performance:
            - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² (vectorized)
            - Nonlinear stiffness: κ(|a|) = κ₀ + κ₂|a|² (vectorized)
            - Susceptibility: χ(|a|) = χ' + iχ''(|a|) (vectorized)

        Args:
            current_block (cp.ndarray): Current solution block on GPU (7D).
            source_block (cp.ndarray): Source term block on GPU (7D).
            block_info: Block information.

        Returns:
            cp.ndarray: Solution block on GPU (7D).

        Raises:
            ValueError: If blocks are not 7D.
        """
        # Verify 7D shape for Level C
        if current_block.ndim != 7:
            raise ValueError(
                f"Expected 7D block for Level C BVP, got {current_block.ndim}D. "
                f"Shape: {current_block.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )
        if source_block.ndim != 7:
            raise ValueError(
                f"Expected 7D source block for Level C BVP, got {source_block.ndim}D. "
                f"Shape: {source_block.shape}."
            )

        # Compute 7D Laplacian using fully vectorized CUDA operations
        h = self.domain.L / self.domain.N  # Grid spacing
        if self._7d_ops is not None:
            # Use optimized 7D Laplacian from CUDABackend7DOps (fully vectorized)
            laplacian_block = self._7d_ops.laplacian_7d(current_block, h=h)
        else:
            # Fallback: compute 7D Laplacian manually with full vectorization
            laplacian_block = self.compute_7d_laplacian_vectorized(current_block, h)

        # Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|² on GPU (fully vectorized)
        amplitude_squared = cp.abs(current_block) ** 2
        stiffness = self.kappa_0 + self.kappa_2 * amplitude_squared

        # Compute divergence term ∇·(κ(|a|)∇a) using fully vectorized operations
        # This is approximated as κ(|a|)Δ₇a for block processing
        div_kappa_grad = stiffness * laplacian_block

        # Compute susceptibility χ(|a|) = χ' + iχ''(|a|) on GPU (fully vectorized)
        amplitude = cp.abs(current_block)
        susceptibility = self.chi_prime + 1j * self.chi_double_prime_0 * amplitude

        # Solve BVP equation: ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s
        # Rearranged: k₀²χ(|a|)a = s - ∇·(κ(|a|)∇a)
        k0_sq = self.k0 ** 2
        rhs = source_block - div_kappa_grad

        # Solve for new solution using fully vectorized operations
        # a_new = (s - ∇·(κ(|a|)∇a)) / (k₀²χ(|a|))
        denominator = k0_sq * susceptibility
        # Vectorized protection against division by zero
        denominator = cp.where(cp.abs(denominator) < 1e-12, 1e-12, denominator)
        solution_block = rhs / denominator

        # Synchronize GPU operations to ensure computation completes
        cp.cuda.Stream.null.synchronize()

        return solution_block

