"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level G CUDA facade.

Provides a unified high-level interface to CUDA-accelerated Level G
operations (cosmological evolution, large-scale structure, and
gravitational effects) with automatic CPU fallback.

Example:
    >>> facade = LevelGCUDAFacade(domain, params)
    >>> a_next = facade.cosmo_evolve_step(a, t, dt)
    >>> ps = facade.compute_power_spectrum(a)
    >>> grav = facade.analyze_gravity(a)
"""

from __future__ import annotations

from typing import Any, Dict
import numpy as np

from .cuda import (
    CosmologicalEvolutionCUDA,
    LargeScaleStructureAnalyzerCUDA,
    GravitationalEffectsCUDA,
)


class LevelGCUDAFacade:
    """
    Facade for CUDA-accelerated Level G computations.
    """

    def __init__(
        self, domain: Any, params: Dict[str, Any], use_cuda: bool = True
    ) -> None:
        self.domain = domain
        self.params = params
        self.cosmo = CosmologicalEvolutionCUDA(
            domain, params, use_cuda=use_cuda
        )
        self.lss = LargeScaleStructureAnalyzerCUDA(
            domain, use_cuda=use_cuda
        )
        self.gravity = GravitationalEffectsCUDA(
            domain, params, use_cuda=use_cuda
        )

    def cosmo_evolve_step(
        self, field: np.ndarray, t: float, dt: float, scale_factor: float = 1.0
    ) -> np.ndarray:
        return self.cosmo.evolve_step(field, t, dt, scale_factor)

    def compute_power_spectrum(
        self, field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        return self.lss.compute_power_spectrum(field)

    def analyze_gravity(self, field: np.ndarray) -> Dict[str, Any]:
        return self.gravity.analyze(field)
