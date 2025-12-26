"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-accelerated Skyrme energy computations for soliton models (Level E).

Brief description: GPU/CPU implementations of Skyrme quartic term energy.

Theoretical Background:
    E_Skyrme = (1/32π²) ∫ Tr([L_μ, L_ν]²) d³x, L_μ = U†∂_μU.

Example:
    >>> sk = SkyrmeEnergyCUDA(S4=0.1)
    >>> energy_gpu = sk.compute_cuda(field_gpu)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:  # pragma: no cover
    cp = None
    CUDA_AVAILABLE = False

if TYPE_CHECKING:
    if CUDA_AVAILABLE and cp is not None:
        CpArray = cp.ndarray
    else:
        from typing import Any as CpArray  # type: ignore
else:
    from typing import Any as CpArray  # type: ignore


class SkyrmeEnergyCUDA:
    """Skyrme energy computations with GPU/CPU backends."""

    def __init__(self, S4: float = 0.1) -> None:
        self.S4 = S4

    def compute_cuda(self, field: CpArray) -> CpArray:
        """Compute Skyrme energy on GPU (CuPy) with CPU-parity reduction.

        This mirrors the CPU algorithm step-by-step using CuPy ops to
        ensure numeric parity (einsum indices, trace reduction, and sums).
        """
        if field.ndim < 4:
            return cp.array(0.0)

        # Pure CuPy implementation with parity-minded reductions
        dx = 0.1
        gradients: list[CpArray] = []
        for i in range(3):
            if field.shape[i] > 1:
                # Match numpy.gradient (default edge handling)
                grad = cp.gradient(field, dx, axis=i)
                gradients.append(grad)
            else:
                gradients.append(cp.zeros_like(field))

        L_currents: list[CpArray] = []
        for grad in gradients:
            L_mu = cp.einsum("...ji,...jk->...ik", cp.conj(field), grad)
            L_currents.append(L_mu)

        skyrme_energy = cp.array(0.0, dtype=cp.float64)
        for i in range(3):
            for j in range(3):
                if i != j:
                    comm = cp.einsum(
                        "...ik,...kj->...ij", L_currents[i], L_currents[j]
                    ) - cp.einsum("...ik,...kj->...ij", L_currents[j], L_currents[i])
                    prod = cp.einsum("...ik,...kj->...ij", comm, comm)
                    # Match numpy.trace default: axes 0,1 (not last two)
                    tr = cp.real(cp.trace(prod))
                    skyrme_energy = skyrme_energy + cp.sum(tr, dtype=cp.float64)

        return skyrme_energy / (32 * np.pi**2)

    def compute_cpu(self, field: np.ndarray) -> float:
        """CPU total Skyrme energy."""
        if field.ndim < 4:
            return 0.0
        dx = 0.1
        gradients = []
        for i in range(3):
            if field.shape[i] > 1:
                grad = np.gradient(field, dx, axis=i)
                gradients.append(grad)
            else:
                gradients.append(np.zeros_like(field))

        L_currents = []
        for grad in gradients:
            L_mu = np.einsum("...ji,...jk->...ik", np.conj(field), grad)
            L_currents.append(L_mu)

        skyrme_energy = 0.0
        for i in range(3):
            for j in range(3):
                if i != j:
                    comm = np.einsum(
                        "...ik,...kj->...ij", L_currents[i], L_currents[j]
                    ) - np.einsum("...ik,...kj->...ij", L_currents[j], L_currents[i])
                    skyrme_energy += np.sum(
                        np.real(np.trace(np.einsum("...ik,...kj->...ij", comm, comm)))
                    )

        return float(skyrme_energy / (32 * np.pi**2))
