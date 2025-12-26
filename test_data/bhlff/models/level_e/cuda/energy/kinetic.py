"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-accelerated kinetic energy computations for soliton models (Level E).

Brief description of the module's purpose and its role in the 7D phase field theory.

Detailed description:
- Provides GPU and CPU implementations for the kinetic energy contribution
- Used by the facade `SolitonEnergyCalculatorCUDA`

Theoretical Background:
    Kinetic term corresponds to time-derivative energy density
    T = (1/2)∫|∂U/∂t|² d³x for complex SU(2)-like field representations.

Example:
    >>> ke = KineticEnergyCUDA()
    >>> energy_density = ke.compute_cuda(field_gpu)
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


class KineticEnergyCUDA:
    """
    Kinetic energy computations for GPU/CPU backends.

    Physical Meaning:
        Computes kinetic energy density based on time derivatives
        of the 7D phase field.
    """

    def compute_cuda(self, field: CpArray) -> CpArray:
        """
        Compute kinetic energy density on GPU.

        Args:
            field: Complex field on GPU with time dimension as last axis.

        Returns:
            CpArray: Kinetic energy density (GPU array).
        """
        if field.ndim < 4:
            return cp.array(0.0)

        dt = 0.01
        if field.shape[-1] > 1:
            dU_dt = cp.gradient(field, dt, axis=-1)
            kinetic_density = 0.5 * cp.real(
                cp.trace(cp.einsum("...ij,...kj->...ik", dU_dt, cp.conj(dU_dt)))
            )
            return kinetic_density
        return cp.array(0.0)

    def compute_cpu(self, field: np.ndarray) -> float:
        """
        Compute kinetic energy (scalar) on CPU.

        Returns:
            float: Total kinetic energy.
        """
        if field.ndim < 4:
            return 0.0
        dt = 0.01
        if field.shape[-1] > 1:
            dU_dt = np.gradient(field, dt, axis=-1)
            kinetic_density = 0.5 * np.real(
                np.trace(np.einsum("...ij,...kj->...ik", dU_dt, np.conj(dU_dt)))
            )
            return float(np.sum(kinetic_density))
        return 0.0
