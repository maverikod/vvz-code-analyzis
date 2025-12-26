"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA block-level energy aggregation for soliton models (Level E).

Aggregates kinetic, Skyrme, and WZW energy contributions per block on GPU.

Example:
    >>> bc = EnergyBlockComputerCUDA(ke, sk, wzw)
    >>> total = bc.compute_block(block_gpu)
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

from .kinetic import KineticEnergyCUDA
from .skyrme import SkyrmeEnergyCUDA
from .wzw import WZWEnergyCUDA


class EnergyBlockComputerCUDA:
    """Compute total energy for a single GPU block."""

    def __init__(
        self, kinetic: KineticEnergyCUDA, skyrme: SkyrmeEnergyCUDA, wzw: WZWEnergyCUDA
    ) -> None:
        self._kinetic = kinetic
        self._skyrme = skyrme
        self._wzw = wzw

    def compute_block(self, block: CpArray) -> CpArray:
        """Compute total energy for block on GPU and return GPU scalar."""
        kinetic = self._kinetic.compute_cuda(block)
        # Kinetic returns density over grid — reduce to scalar
        kinetic_total = cp.sum(kinetic) if kinetic.ndim > 0 else kinetic

        skyrme = self._skyrme.compute_cuda(block)  # scalar (cp.array)
        wzw = self._wzw.compute_cuda(block)  # scalar (cp.array)

        total = kinetic_total + skyrme + wzw
        return total
