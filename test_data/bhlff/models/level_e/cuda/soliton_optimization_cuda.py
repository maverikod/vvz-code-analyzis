"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized optimization methods for soliton models.

This module provides GPU-accelerated soliton optimization with block processing
and vectorized operations for maximum performance.

Physical Meaning:
    Finds stable soliton solutions using GPU-accelerated optimization
    algorithms that minimize the energy functional with block processing.

Mathematical Foundation:
    Solves δE/δU = 0 using GPU-accelerated Newton-Raphson method
    with block-based processing using 80% of GPU memory.
"""

import numpy as np
from typing import Dict, Any, TYPE_CHECKING
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

if TYPE_CHECKING:
    if CUDA_AVAILABLE and cp is not None:
        CpArray = cp.ndarray
    else:
        CpArray = Any
else:
    CpArray = Any

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend, CPUBackend
from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor
from ..soliton_optimization import ConvergenceError
from .soliton_energy_cuda import SolitonEnergyCalculatorCUDA


class SolitonOptimizerCUDA:
    """
    CUDA-optimized optimizer for soliton models.

    Physical Meaning:
        Finds stable soliton solutions using GPU-accelerated optimization
        algorithms with block processing and vectorization.
    """

    def __init__(
        self, domain: "Domain", physics_params: Dict[str, Any], use_cuda: bool = True
    ):
        """Initialize CUDA optimizer."""
        self.domain = domain
        self.params = physics_params
        self.logger = logging.getLogger(__name__)
        self.use_cuda = use_cuda and CUDA_AVAILABLE

        # Initialize backend
        if self.use_cuda:
            try:
                self.backend = get_optimal_backend()
                self.cuda_available = isinstance(self.backend, CUDABackend)
            except Exception:
                self.backend = CPUBackend()
                self.cuda_available = False
        else:
            self.backend = CPUBackend()
            self.cuda_available = False

        # Initialize energy calculator
        self.energy_calc = SolitonEnergyCalculatorCUDA(domain, physics_params, use_cuda)

        # Compute optimal block size
        self.block_size = self._compute_optimal_block_size()

        if self.cuda_available:
            self.block_processor = CUDABlockProcessor(
                domain, block_size=self.block_size
            )
        else:
            self.block_processor = None

    def _compute_optimal_block_size(self) -> int:
        """Compute optimal block size (80% GPU memory)."""
        if not self.cuda_available:
            return 8

        try:
            if isinstance(self.backend, CUDABackend):
                mem_info = self.backend.get_memory_info()
                available_memory_bytes = int(mem_info["free_memory"] * 0.8)
                bytes_per_element = 16
                overhead_factor = 10  # Field + gradients + hessian
                max_elements = available_memory_bytes // (
                    bytes_per_element * overhead_factor
                )
                elements_per_dim = int(max_elements ** (1.0 / 7.0))
                return max(4, min(elements_per_dim, 128))
            return 8
        except Exception:
            return 8

    def find_solution(self, initial_guess: np.ndarray) -> np.ndarray:
        """
        Find soliton solution using CUDA-accelerated optimization.

        Physical Meaning:
            Searches for stable localized field configurations using
            GPU-accelerated Newton-Raphson method with block processing.
        """
        if self.cuda_available:
            return self._solve_stationary_equation_cuda(initial_guess)
        else:
            return self._solve_stationary_equation_cpu(initial_guess)

    def _solve_stationary_equation_cuda(self, initial_guess: np.ndarray) -> np.ndarray:
        """Solve using CUDA-accelerated Newton-Raphson."""
        U = self.backend.array(initial_guess.copy())
        tolerance = 1e-8
        max_iterations = 1000

        try:
            for iteration in range(max_iterations):
                # Compute residual (vectorized on GPU)
                F = self._compute_energy_gradient_cuda(U)

                # Check convergence
                residual_norm = float(cp.linalg.norm(F))
                if iteration % 10 == 0 or residual_norm < tolerance:
                    self.logger.info(
                        f"[OptimizerCUDA] iter={iteration} residual={residual_norm:.3e}"
                    )
                if residual_norm < tolerance:
                    break

                # Compute Jacobian (block processing)
                J = self._compute_energy_hessian_cuda(U)

                # Solve Newton step (GPU linear algebra)
                try:
                    delta_U = cp.linalg.solve(J, -F)
                except cp.linalg.LinAlgError:
                    delta_U = -cp.linalg.pinv(J) @ F

                # Update with line search
                U = self._update_with_line_search_cuda(U, delta_U, F)
                if iteration % 10 == 0:
                    step_norm = float(cp.linalg.norm(delta_U))
                    self.logger.info(
                        f"[OptimizerCUDA] step_norm={step_norm:.3e} (after line search)"
                    )

            if iteration == max_iterations - 1:
                raise ConvergenceError(
                    f"Failed to converge after {max_iterations} iterations"
                )

            return cp.asnumpy(U)

        finally:
            if self.cuda_available:
                cp.get_default_memory_pool().free_all_blocks()

    def _compute_energy_gradient_cuda(self, field: CpArray) -> CpArray:
        """Compute energy gradient on GPU (vectorized)."""
        # Use energy calculator's gradient computation
        gradient = cp.zeros_like(field)

        # Add contributions (vectorized operations)
        gradient += self._compute_kinetic_gradient_cuda(field)
        gradient += self._compute_skyrme_gradient_cuda(field)
        gradient += self._compute_wzw_gradient_cuda(field)

        return gradient

    def _compute_energy_hessian_cuda(self, field: CpArray) -> CpArray:
        """Compute Hessian on GPU with block processing."""
        # Block-based Hessian computation for memory efficiency
        n = field.size
        hessian = cp.zeros((n, n), dtype=cp.complex128)

        # Process in blocks to fit in GPU memory
        block_size = min(100, n // 4)  # Process 1/4 at a time

        for i_start in range(0, n, block_size):
            i_end = min(i_start + block_size, n)
            for j_start in range(0, n, block_size):
                j_end = min(j_start + block_size, n)

                # Compute block of Hessian
                hessian_block = self._compute_hessian_block_cuda(
                    field, i_start, i_end, j_start, j_end
                )
                hessian[i_start:i_end, j_start:j_end] = hessian_block

        return hessian

    def _compute_hessian_block_cuda(
        self, field: CpArray, i_start: int, i_end: int, j_start: int, j_end: int
    ) -> CpArray:
        """Compute a block of the Hessian matrix on GPU."""
        epsilon = 1e-6
        block = cp.zeros((i_end - i_start, j_end - j_start), dtype=cp.complex128)

        E0 = self.energy_calc.compute_total_energy(cp.asnumpy(field))

        for i_idx, i in enumerate(range(i_start, i_end)):
            for j_idx, j in enumerate(range(j_start, j_end)):
                field_pp = field.copy()
                field_pp.flat[i] += epsilon
                field_pp.flat[j] += epsilon
                E_pp = self.energy_calc.compute_total_energy(cp.asnumpy(field_pp))

                field_pm = field.copy()
                field_pm.flat[i] += epsilon
                field_pm.flat[j] -= epsilon
                E_pm = self.energy_calc.compute_total_energy(cp.asnumpy(field_pm))

                field_mp = field.copy()
                field_mp.flat[i] -= epsilon
                field_mp.flat[j] += epsilon
                E_mp = self.energy_calc.compute_total_energy(cp.asnumpy(field_mp))

                field_mm = field.copy()
                field_mm.flat[i] -= epsilon
                field_mm.flat[j] -= epsilon
                E_mm = self.energy_calc.compute_total_energy(cp.asnumpy(field_mm))

                block[i_idx, j_idx] = (E_pp - E_pm - E_mp + E_mm) / (4 * epsilon**2)

        return block

    def _update_with_line_search_cuda(
        self, U: CpArray, delta_U: CpArray, F: CpArray
    ) -> CpArray:
        """Update solution with line search on GPU."""
        alpha = 1.0
        max_iterations = 10

        for _ in range(max_iterations):
            U_new = U + alpha * delta_U
            E_new = self.energy_calc.compute_total_energy(cp.asnumpy(U_new))
            E_old = self.energy_calc.compute_total_energy(cp.asnumpy(U))

            if E_new < E_old:
                return U_new

            alpha *= 0.5

        return U + alpha * delta_U

    def _compute_kinetic_gradient_cuda(self, field: CpArray) -> CpArray:
        """
        Compute kinetic gradient on GPU.

        Physical Meaning:
            Calculates gradient of kinetic energy term with respect to field.

        Mathematical Foundation:
            δT/δU = -∂²U/∂t² where T = (1/2)∫|∂U/∂t|² d³x
        """
        if field.ndim < 4 or field.shape[-1] <= 1:
            return cp.zeros_like(field)

        dt = 0.01
        # Compute second time derivative (vectorized)
        dU_dt = cp.gradient(field, dt, axis=-1)
        d2U_dt2 = cp.gradient(dU_dt, dt, axis=-1)

        # Gradient is negative second time derivative
        gradient = -d2U_dt2

        return gradient * self.params.get("F2", 1.0) ** 2 * 0.5

    def _compute_skyrme_gradient_cuda(self, field: CpArray) -> CpArray:
        """
        Compute Skyrme gradient on GPU using numerical differentiation for correctness.

        Physical Meaning:
            Finite-difference directional derivatives of the Skyrme energy.
        """
        # Full variational Skyrme gradient via residual R = D_i K^i - [K^i, L_i]
        if field.ndim < 4:
            return cp.zeros_like(field)

        dx = 0.1
        S4 = self.params.get("S4", 0.1)

        # Project to unitary: U = F (F†F)^(-1/2)
        F = field
        H = cp.einsum("...ji,...jk->...ik", cp.conj(F), F)
        w, V = cp.linalg.eigh(H)
        w = cp.clip(w, 1e-12, None)
        w_inv_sqrt = 1.0 / cp.sqrt(w)
        Vh = cp.swapaxes(V, -2, -1).conj()
        V_scaled = V * w_inv_sqrt[..., None, :]
        S = V_scaled @ Vh
        U = F @ S

        # Spatial derivatives and left currents L_i = U† ∂_i U
        grads: list[CpArray] = []
        for i in range(3):
            if U.shape[i] > 1:
                grads.append(cp.gradient(U, dx, axis=i))
            else:
                grads.append(cp.zeros_like(U))

        Ls: list[CpArray] = []
        U_dag = cp.swapaxes(U, -2, -1).conj()
        for g in grads:
            Ls.append(cp.einsum("...ji,...jk->...ik", U_dag, g))

        # K^i_(4) = -S4 sum_j [L_j, [L_i, L_j]]
        Ks: list[CpArray] = []
        for i in range(3):
            K_i = cp.zeros_like(Ls[i])
            L_i = Ls[i]
            for j in range(3):
                L_j = Ls[j]
                inner = cp.einsum("...ik,...kj->...ij", L_i, L_j) - cp.einsum(
                    "...ik,...kj->...ij", L_j, L_i
                )
                outer = cp.einsum("...ik,...kj->...ij", L_j, inner) - cp.einsum(
                    "...ik,...kj->...ij", inner, L_j
                )
                K_i = K_i - S4 * outer
            Ks.append(K_i)

        # Residual R = sum_i ( D_i K^i - [K^i, L_i] ), with D_i K^i = ∂_i K^i + [L_i, K^i]
        R = cp.zeros_like(Ks[0])
        for i in range(3):
            K_i = Ks[i]
            L_i = Ls[i]
            dKi = (
                cp.gradient(K_i, dx, axis=i)
                if field.shape[i] > 1
                else cp.zeros_like(K_i)
            )
            comm_LK = cp.einsum("...ik,...kj->...ij", L_i, K_i) - cp.einsum(
                "...ik,...kj->...ij", K_i, L_i
            )
            # D_i K^i - [K^i, L_i] = ∂_i K^i + [L_i, K^i] - [K^i, L_i] = ∂_i K^i + 2 [L_i, K^i]
            R = R + dKi + 2.0 * comm_LK

        # Map algebra residual to field space: δE/δU ∝ U R
        grad = cp.einsum("...ij,...jk->...ik", U, R)
        return grad / (32 * np.pi**2)

    def _compute_wzw_gradient_cuda(self, field: CpArray) -> CpArray:
        """
        Compute WZW gradient on GPU.

        Physical Meaning:
            Calculates gradient of WZW energy term with respect to field.

        Mathematical Foundation:
            δE_WZW/δU involves variation of U(1)^3 phase winding terms.
        """
        if field.ndim < 7 or field.shape[-3:] != (8, 8, 8):
            return cp.zeros_like(field)

        # WZW gradient is related to phase divergence
        dphi = 2 * np.pi / 8
        gradient = cp.zeros_like(field)

        # Compute phase gradients
        phase_gradients = []
        for i in range(3):
            grad = cp.gradient(field, dphi, axis=-(3 - i))
            phase_gradients.append(grad)

        # Gradient is proportional to divergence of phase gradients
        for alpha in range(3):
            gradient += phase_gradients[alpha]

        return gradient * (dphi**3) / (8 * np.pi**2)

    def _solve_stationary_equation_cpu(self, initial_guess: np.ndarray) -> np.ndarray:
        """
        Solve stationary equation using CPU (Newton-Raphson).

        Physical Meaning:
            Finds field configuration that minimizes energy functional
            using CPU-based Newton-Raphson method.

        Mathematical Foundation:
            Iteratively solves F(U) = δE/δU = 0 using Newton's method.
        """
        from ..soliton_optimization import SolitonOptimizer

        # Use CPU optimizer
        cpu_optimizer = SolitonOptimizer(self.domain, self.params)
        return cpu_optimizer.find_solution(initial_guess)
