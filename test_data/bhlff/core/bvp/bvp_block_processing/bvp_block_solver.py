"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP block solver for 7D phase field theory.

This module implements 7D stencil-based iterative solver for BVP blocks,
using amplitude-dependent coefficients and physically meaningful boundary
conditions, preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    Solves the BVP envelope equation for a single block:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    using 7D Laplacian over all dimensions (3 spatial + 3 phase + 1 temporal)
    with proper boundary conditions and amplitude-dependent coefficients.

Mathematical Foundation:
    Implements Jacobi/Gauss-Seidel iterative solver with 7D finite difference stencil:
    Δ₇a = Σᵢ₌₀⁶ (a[i+1] - 2a[i] + a[i-1]) / h²ᵢ
    where i runs over all 7 dimensions (x,y,z,φ₁,φ₂,φ₃,t).
"""

import numpy as np
from typing import Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .bvp_block_coefficients import BVPBlockCoefficients
from .bvp_block_boundary_conditions import BVPBlockBoundaryConditions


class BVPBlockSolver:
    """
    BVP block solver for 7D phase field theory.

    Physical Meaning:
        Solves the BVP envelope equation for a single block:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
        using 7D Laplacian over all dimensions (3 spatial + 3 phase + 1 temporal)
        with proper boundary conditions and amplitude-dependent coefficients.

    Mathematical Foundation:
        Implements Jacobi/Gauss-Seidel iterative solver with 7D finite difference stencil:
        Δ₇a = Σᵢ₌₀⁶ (a[i+1] - 2a[i] + a[i-1]) / h²ᵢ
        where i runs over all 7 dimensions (x,y,z,φ₁,φ₂,φ₃,t).
    """

    def __init__(self, coefficients: BVPBlockCoefficients = None,
                 boundary_conditions: BVPBlockBoundaryConditions = None,
                 h_sq: float = 1.0, num_iters: int = 15, omega: float = 1.0):
        """
        Initialize BVP block solver.

        Args:
            coefficients: BVP block coefficients computer.
            boundary_conditions: BVP block boundary conditions computer.
            h_sq (float): Grid spacing squared.
            num_iters (int): Number of iterations.
            omega (float): Relaxation parameter (1.0 = Jacobi, 1.0-2.0 = Gauss-Seidel/SOR).
        """
        self.coefficients = coefficients or BVPBlockCoefficients()
        self.boundary_conditions = boundary_conditions or BVPBlockBoundaryConditions()
        self.h_sq = h_sq
        self.num_iters = num_iters
        self.omega = omega

    def solve(
        self, envelope_block: np.ndarray, source_block: np.ndarray,
        block_info: Any = None, use_cuda: bool = False
    ) -> np.ndarray:
        """
        Solve BVP equation for a single block using 7D stencil-based iterative solver.

        Physical Meaning:
            Solves the BVP envelope equation for a single block:
            ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
            using 7D Laplacian over all dimensions (3 spatial + 3 phase + 1 temporal)
            with proper boundary conditions and amplitude-dependent coefficients.

        Mathematical Foundation:
            Implements Jacobi/Gauss-Seidel iterative solver with 7D finite difference stencil:
            Δ₇a = Σᵢ₌₀⁶ (a[i+1] - 2a[i] + a[i-1]) / h²ᵢ
            where i runs over all 7 dimensions (x,y,z,φ₁,φ₂,φ₃,t).

        Args:
            envelope_block (np.ndarray): Current envelope solution block (7D).
            source_block (np.ndarray): Source term block (7D).
            block_info: Block information with start/end indices.
            use_cuda (bool): Whether to use CUDA acceleration.

        Returns:
            np.ndarray: Updated envelope solution block (7D).
        """
        if use_cuda and CUDA_AVAILABLE:
            return self._solve_cuda(envelope_block, source_block, block_info)
        else:
            return self._solve_cpu(envelope_block, source_block, block_info)

    def _solve_cpu(
        self, envelope_block: np.ndarray, source_block: np.ndarray, block_info: Any
    ) -> np.ndarray:
        """CPU implementation of 7D stencil-based iterative solver."""
        # Ensure correct dtype
        a = envelope_block.astype(np.complex128, copy=True)
        s = source_block.astype(np.complex128, copy=False)

        # Compute amplitude-dependent coefficients
        # All coefficients computed element-wise on 7D block, ensuring correct shape
        amplitude = np.abs(a)

        # Verify 7D structure
        if a.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block for BVP solving, got {a.ndim}D. "
                f"Shape: {a.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Compute coefficients - all return arrays with same 7D shape as input
        # No broadcasting needed - methods compute element-wise on 7D block
        kappa = self.coefficients.compute_stiffness(amplitude, block_info)
        chi = self.coefficients.compute_susceptibility(amplitude, block_info)
        bc_term = self.boundary_conditions.apply_boundary_conditions(a, block_info)

        # Verify shapes match (should always match if methods implemented correctly)
        if kappa.shape != a.shape:
            raise ValueError(
                f"Stiffness shape {kappa.shape} does not match envelope shape {a.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )
        if chi.shape != a.shape:
            raise ValueError(
                f"Susceptibility shape {chi.shape} does not match envelope shape {a.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )
        if bc_term.shape != a.shape:
            raise ValueError(
                f"Boundary condition shape {bc_term.shape} does not match envelope shape {a.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )

        # Iterative solver
        for iteration in range(self.num_iters):
            # Compute 7D Laplacian using finite difference stencil
            # All 7 dimensions: spatial (0,1,2) + phase (3,4,5) + temporal (6)
            lap = np.zeros_like(a)

            # All 7 dimensions vectorized
            for axis in range(7):
                lap += (np.roll(a, 1, axis=axis) - 2.0 * a + np.roll(a, -1, axis=axis)) / self.h_sq

            # Compute divergence term: ∇·(κ(|a|)∇a)
            # Simplified: κ∇²a + ∇κ·∇a ≈ κ∇²a (for small gradients of κ)
            div_kappa_grad = kappa * lap

            # Update equation: a_new = (s - ∇·(κ∇a) - bc_term) / (k₀²χ + regularization)
            k0_sq = 1.0  # Can be made configurable
            denominator = k0_sq * chi + bc_term
            denominator = np.where(np.abs(denominator) < 1e-12, 1e-12, denominator)

            # Jacobi update with relaxation
            a_new = (s - div_kappa_grad - bc_term * a) / denominator
            a = self.omega * a_new + (1.0 - self.omega) * a

        return a

    def _solve_cuda(
        self, envelope_block: np.ndarray, source_block: np.ndarray, block_info: Any
    ) -> np.ndarray:
        """CUDA implementation of 7D stencil-based iterative solver with vectorization."""
        # Transfer to GPU
        a_gpu = cp.asarray(envelope_block.astype(np.complex128))
        s_gpu = cp.asarray(source_block.astype(np.complex128))
        cp.cuda.Stream.null.synchronize()

        # Verify 7D structure on GPU
        if a_gpu.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block for CUDA BVP solving, got {a_gpu.ndim}D. "
                f"Shape: {a_gpu.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Compute amplitude on GPU (vectorized)
        amplitude_gpu = cp.abs(a_gpu)

        # Compute coefficients on GPU - all computed element-wise on 7D block
        # Transfer to CPU for computation, then back to GPU (methods use NumPy)
        # In future optimization, these can be computed directly on GPU
        kappa_gpu = cp.asarray(
            self.coefficients.compute_stiffness(cp.asnumpy(amplitude_gpu), block_info)
        )
        chi_gpu = cp.asarray(
            self.coefficients.compute_susceptibility(cp.asnumpy(amplitude_gpu), block_info)
        )
        bc_term_gpu = cp.asarray(
            self.boundary_conditions.apply_boundary_conditions(cp.asnumpy(a_gpu), block_info)
        )

        # Verify shapes match (should always match if methods implemented correctly)
        # No broadcasting - all methods return arrays with same 7D shape
        if kappa_gpu.shape != a_gpu.shape:
            raise ValueError(
                f"Stiffness shape {kappa_gpu.shape} does not match envelope shape {a_gpu.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )
        if chi_gpu.shape != a_gpu.shape:
            raise ValueError(
                f"Susceptibility shape {chi_gpu.shape} does not match envelope shape {a_gpu.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )
        if bc_term_gpu.shape != a_gpu.shape:
            raise ValueError(
                f"Boundary condition shape {bc_term_gpu.shape} does not match envelope shape {a_gpu.shape}. "
                f"Expected same 7D shape for element-wise operations."
            )

        # Iterative solver
        for iteration in range(self.num_iters):
            # 7D Laplacian on GPU (vectorized)
            lap = cp.zeros_like(a_gpu)

            # All 7 dimensions vectorized
            for axis in range(7):
                lap += (cp.roll(a_gpu, 1, axis=axis) - 2.0 * a_gpu + cp.roll(a_gpu, -1, axis=axis)) / self.h_sq

            # Divergence term
            div_kappa_grad = kappa_gpu * lap

            # Update
            k0_sq = 1.0
            denominator = k0_sq * chi_gpu + bc_term_gpu
            denominator = cp.where(cp.abs(denominator) < 1e-12, 1e-12, denominator)

            a_new = (s_gpu - div_kappa_grad - bc_term_gpu * a_gpu) / denominator
            a_gpu = self.omega * a_new + (1.0 - self.omega) * a_gpu

        # Synchronize and transfer back
        cp.cuda.Stream.null.synchronize()
        result = cp.asnumpy(a_gpu)
        return result

