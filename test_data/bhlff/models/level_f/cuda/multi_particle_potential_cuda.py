"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-accelerated multi-particle potential analyzer for Level F.

This module implements a GPU-optimized computation of effective potentials
for multi-particle systems with strict memory-aware block processing that
targets 80% of available GPU memory. It leverages CuPy for vectorized
operations and integrates with the 7D block processing tools.

Physical Meaning:
    Computes the effective potential for systems of multiple topological
    defects interacting via a step-resonator model. The potential includes
    single-particle, pair-wise, and higher-order (three-body) terms.

Mathematical Foundation:
    U_eff = \\sum_i U_i + \\sum_{i<j} U_{ij} + \\sum_{i<j<k} U_{ijk}
    where the interactions follow a step potential with cutoff r_cutoff.

Example:
    >>> analyzer = MultiParticlePotentialAnalyzerCUDA(
    ...     domain,
    ...     particles,
    ...     interaction_range=5.0,
    ...     params={"interaction_strength": 1.0},
    ... )
    >>> potential = analyzer.compute_effective_potential()
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:  # pragma: no cover
    cp = None
    CUDA_AVAILABLE = False

from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor
from bhlff.utils.cuda_utils import CUDABackend, get_optimal_backend
from ..multi_particle.data_structures import Particle, SystemParameters


class MultiParticlePotentialAnalyzerCUDA:
    """
    CUDA-accelerated potential analyzer for multi-particle systems.

    Physical Meaning:
        Computes the effective potential of a multi-particle system on GPU
        using vectorized CuPy operations with block processing sized to use
        approximately 80% of free GPU memory without out-of-memory errors.

    Mathematical Foundation:
        Implements step-resonator interactions for single, pair, and three-body
        terms and aggregates their contributions over the computational domain.

    Attributes:
        domain: Computational domain with attributes `L`, `N`, `shape`.
        particles: List of `Particle` objects describing the system.
        interaction_range: Cutoff radius r_cutoff for step interactions.
        params: Additional parameters, including `interaction_strength`.
        system_params: Optional `SystemParameters`
            for consistency with CPU path.
    """

    def __init__(
        self,
        domain: Any,
        particles: List[Particle],
        interaction_range: float = 2.0,
        params: Optional[Dict[str, Any]] = None,
        system_params: Optional[SystemParameters] = None,
    ) -> None:
        """
        Initialize the CUDA analyzer.

        Physical Meaning:
            Sets up GPU backend and block processor for memory-safe computation
            of the effective potential across the full domain.

        Args:
            domain: Computational domain instance.
            particles (List[Particle]):
                Particles participating in interactions.
            interaction_range (float): Cutoff for step interactions.
            params (Optional[Dict[str, Any]]): Additional parameters.
            system_params (Optional[SystemParameters]):
                System-level parameters.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA not available for MultiParticlePotentialAnalyzerCUDA"
            )

        self.logger = logging.getLogger(__name__)
        self.domain = domain
        self.particles = particles
        self.interaction_range = float(interaction_range)
        self.params: Dict[str, Any] = params or {}
        self.system_params = system_params or SystemParameters()

        # Select optimal backend (will be CUDA when available)
        backend = get_optimal_backend()
        if not isinstance(backend, CUDABackend):
            raise RuntimeError(
                "CUDA backend not selected; cannot construct CUDA analyzer"
            )
        self.backend = backend

        # Optional tuning parameters
        self.memory_fraction = float(self.params.get("memory_fraction", 0.8))
        self.device_id = int(self.params.get("device_id", cp.cuda.Device().id))
        self.precision = str(self.params.get("precision", "float64")).lower()
        self._dtype = cp.float32 if self.precision == "float32" else cp.float64

        # Select target device (if provided)
        cp.cuda.Device(self.device_id).use()

        # Determine optimal block size targeting ~80% free GPU memory
        self.block_size = self._compute_optimal_block_size_7d()

        # Try to initialize CUDA block processor (7D); if domain is not 7D, fall back to 3D iterator
        self.block_processor = None
        try:
            # Many core processors enforce 7D domains; keep optional
            self.block_processor = CUDABlockProcessor(domain, block_size=self.block_size)
        except Exception:
            self.block_processor = None

        # Cache particle data on GPU
        self._positions_gpu = cp.asarray(
            [p.position for p in self.particles], dtype=self._dtype
        )
        self._charges_gpu = cp.asarray(
            [float(p.charge) for p in self.particles], dtype=self._dtype
        )

        # Precompute close pairs and triples once to avoid per-block checks
        self._close_pairs: List[tuple[int, int]] = []
        self._close_triples: List[tuple[int, int, int]] = []
        try:
            pos = self._positions_gpu  # (n,3)
            diffs = pos[:, None, :] - pos[None, :, :]  # (n,n,3)
            d2 = cp.sum(diffs * diffs, axis=-1)
            mask_pairs = (d2 < (self.interaction_range**2)).astype(cp.bool_)
            mp = cp.asnumpy(mask_pairs)
            n = mp.shape[0]
            for i in range(n):
                for j in range(i + 1, n):
                    if mp[i, j]:
                        self._close_pairs.append((i, j))
            for i in range(n):
                for j in range(i + 1, n):
                    if not mp[i, j]:
                        continue
                    for k in range(j + 1, n):
                        if mp[i, k] and mp[j, k]:
                            self._close_triples.append((i, j, k))
        except Exception:
            self._close_pairs = []
            self._close_triples = []

    def compute_effective_potential(self) -> np.ndarray:
        """
        Compute the effective potential field on GPU with block processing.

        Physical Meaning:
            Aggregates contributions from single, pair, and three-body
            interactions across the entire domain using memory-aware
            CUDA block processing.

        Returns:
            np.ndarray: Effective potential on CPU memory with spatial shape (N, N, N).
        """
        # Preallocate on CPU; assemble per block to reduce GPU pressure
        result = np.zeros(
            (int(self.domain.N), int(self.domain.N), int(self.domain.N)),
            dtype=np.float64,
        )

        positions = self._positions_gpu
        charges = self._charges_gpu

        # Grid coordinates (per-block will slice views to minimize allocations)
        x = cp.linspace(0.0, float(self.domain.L), int(self.domain.N))
        y = cp.linspace(0.0, float(self.domain.L), int(self.domain.N))
        z = cp.linspace(0.0, float(self.domain.L), int(self.domain.N))

        # Iterate CUDA blocks by indices; slice coordinates to each block
        block_id = 0
        block_iter = None
        if self.block_processor is not None and getattr(self.block_processor, "cuda_available", True):
            try:
                block_iter = ((bi.start_indices, bi.end_indices) for _, bi in self.block_processor.iterate_blocks_cuda())
            except Exception:
                block_iter = None
        if block_iter is None:
            # Fallback to simple 3D iterator over spatial grid
            def _iter_blocks_3d(N: int, bs: int):
                for i0 in range(0, N, bs):
                    i1 = int(min(N, i0 + bs))
                    for j0 in range(0, N, bs):
                        j1 = int(min(N, j0 + bs))
                        for k0 in range(0, N, bs):
                            k1 = int(min(N, k0 + bs))
                            yield (i0, j0, k0), (i1, j1, k1)
            block_iter = _iter_blocks_3d(int(self.domain.N), int(self.block_size))

        for start, end in block_iter:
            # Compute block slices
            slices = tuple(slice(s, e) for s, e in zip(start, end))

            # Coordinate sub-grids for this block
            Xb, Yb, Zb = cp.meshgrid(
                x[slices[0]], y[slices[1]], z[slices[2]], indexing="ij"
            )

            # Accumulate block potential on GPU
            block_potential = cp.zeros(Xb.shape, dtype=self._dtype)

            # Single-particle contributions via sub-batching (vectorized)
            strength = float(self.params.get("interaction_strength", 1.0))
            r_cut = self.interaction_range
            rc2 = r_cut * r_cut

            n = positions.shape[0]
            mem = self.backend.get_memory_info()
            free_bytes = int(mem.get("free_memory", 0))
            if free_bytes <= 0:
                subbatch = min(n, 32)
            else:
                elements_per_block = int(Xb.size)
                bytes_per_element = 4 if self._dtype == cp.float32 else 8
                budget = max(1, int(0.1 * free_bytes))
                est_per_particle = elements_per_block * bytes_per_element * 6
                subbatch = max(1, min(n, budget // max(1, est_per_particle)))
                subbatch = int(min(subbatch, 128))

            rc2 = r_cut * r_cut
            for p0 in range(0, n, subbatch):
                p1 = min(n, p0 + subbatch)
                px = positions[p0:p1, 0]
                py = positions[p0:p1, 1]
                pz = positions[p0:p1, 2]
                cq = charges[p0:p1]

                dx = Xb[..., None] - px[None, None, None, :]
                dy = Yb[..., None] - py[None, None, None, :]
                dz = Zb[..., None] - pz[None, None, None, :]
                r2 = dx * dx + dy * dy + dz * dz
                mask = r2 < rc2  # squared distance thresholding
                weighted = mask.astype(self._dtype) * cq[None, None, None, :]
                contrib = weighted.sum(axis=-1)
                block_potential += strength * contrib

            # Pair-wise uniform contributions using precomputed adjacency
            for i, j in self._close_pairs:
                block_potential += strength

            # Three-body uniform contributions using precomputed adjacency
            for i, j, k in self._close_triples:
                block_potential += strength

            # Bring block result to CPU and insert
            result[slices[0], slices[1], slices[2]] = cp.asnumpy(block_potential)

            # Periodic cleanup to respect memory budget
            if block_id % 8 == 0:
                cp.get_default_memory_pool().free_all_blocks()
            block_id += 1

        # Final cleanup of GPU memory pools
        cp.get_default_memory_pool().free_all_blocks()
        cp.get_default_pinned_memory_pool().free_all_blocks()

        return result

    def _compute_optimal_block_size_7d(self) -> int:
        """
        Compute block size per dimension using ~80% of free GPU memory.

        Physical Meaning:
            Ensures that all intermediate arrays within a block fit
            into GPU memory with safety margin while maximizing throughput.

        Returns:
            int: Block size per spatial dimension (clamped to domain dims).
        """
        mem = self.backend.get_memory_info()
        free_bytes = int(mem.get("free_memory", 0))
        usable = int(free_bytes * self.memory_fraction)  # target fraction

        arrays_per_element = 8
        bytes_per_element = 8  # conservative upper bound
        budget_per_element = arrays_per_element * bytes_per_element

        max_elements = usable // budget_per_element
        if max_elements <= 0:
            return 4

        side = int(max_elements ** (1.0 / 3.0))

        side = max(4, min(side, 256))
        side = min(
            side,
            int(self.domain.shape[0]),
            int(self.domain.shape[1]),
            int(self.domain.shape[2]),
        )

        return max(4, side)
