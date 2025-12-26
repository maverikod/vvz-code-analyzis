"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-accelerated WZW energy computations for soliton models (Level E).

Brief: GPU/CPU implementations of U(1)^3 WZW term energy over phase torus.

Theoretical Background:
    E_WZW = (1/8π²) ∫_{T^3_φ} dφ₁ dφ₂ dφ₃ ∇_φ · Θ(x, φ).

Example:
    >>> wzw = WZWEnergyCUDA()
    >>> e_gpu = wzw.compute_cuda(field_gpu)
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


class WZWEnergyCUDA:
    """WZW energy computations with GPU/CPU backends."""

    def compute_cuda(self, field: CpArray) -> CpArray:
        """Compute WZW energy (GPU scalar)."""
        if field.ndim < 7:
            return cp.array(0.0)
        if field.shape[-3:] != (8, 8, 8):
            return cp.array(0.0)

        dphi = 2 * np.pi / 8
        phase_gradients = []
        for i in range(3):
            grad = cp.gradient(field, dphi, axis=-(3 - i))
            phase_gradients.append(grad)

        div_phase = cp.zeros_like(field[..., 0, 0, 0])
        for alpha in range(3):
            div_phase += cp.sum(phase_gradients[alpha], axis=tuple(range(-3, 0)))

        wzw_energy = cp.sum(div_phase) * (dphi**3) / (8 * np.pi**2)
        return cp.real(wzw_energy)

    def compute_cpu(self, field: np.ndarray) -> float:
        """CPU total WZW energy via vectorized divergence over phase torus."""
        if field.ndim < 7:
            return 0.0
        if field.shape[-3:] != (8, 8, 8):
            return 0.0
        dphi = 2 * np.pi / 8
        phase_gradients = []
        for i in range(3):
            grad = np.gradient(field, dphi, axis=-(3 - i))
            phase_gradients.append(grad)
        div_phase = np.zeros_like(field[..., 0, 0, 0])
        for alpha in range(3):
            div_phase += np.sum(phase_gradients[alpha], axis=tuple(range(-3, 0)))
        wzw_energy = np.sum(div_phase) * (dphi**3) / (8 * np.pi**2)
        return float(np.real(wzw_energy))
