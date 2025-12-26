"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized CPU block processing for multi-particle effective potential.

This module provides a memory-aware, vectorized CPU implementation of the
single-particle contribution to the effective potential on a 3D spatial grid,
including uniform adjustments for precomputed pair and three-body adjacency.

Physical Meaning:
    Aggregates contributions from particles within a cutoff radius using
    a step-resonator interaction model on a 3D domain grid.

Example:
    result = compute_potential_blocked(domain, positions, charges, 5.0, 1.0, 64,
                                       num_pairs=len(close_pairs),
                                       num_triples=len(close_triples))
"""

from __future__ import annotations

from typing import Any
import numpy as np


def compute_potential_blocked(
    domain: Any,
    positions: np.ndarray,
    charges: np.ndarray,
    interaction_range: float,
    strength: float,
    cpu_block_size: int,
    *,
    num_pairs: int = 0,
    num_triples: int = 0,
) -> np.ndarray:
    """
    Compute effective potential on CPU using vectorized block processing.

    Args:
        domain: Domain-like object with attributes `N` and `L` (scalar or tuple).
        positions: Array of shape (n, 3) with particle coordinates.
        charges: Array of shape (n,) with particle charges.
        interaction_range: Cutoff radius for step interaction.
        strength: Interaction strength multiplier.
        cpu_block_size: Side of cubic processing block in grid points.
        num_pairs: Number of close particle pairs for uniform contribution.
        num_triples: Number of close particle triples for uniform contribution.

    Returns:
        np.ndarray: Effective potential field of shape (N, N, N), float64.
    """
    N = int(domain.N)
    spatial_shape = (N, N, N)
    result = np.zeros(spatial_shape, dtype=np.float64)

    if positions.size == 0:
        return result

    L = getattr(domain, "L", N)
    Lval = float(L[0] if hasattr(L, "__len__") else L)
    x = np.linspace(0.0, Lval, N)
    y = np.linspace(0.0, Lval, N)
    z = np.linspace(0.0, Lval, N)

    r_cut2 = float(interaction_range) * float(interaction_range)
    n_particles = int(positions.shape[0])
    cpu_block_size = int(max(8, min(cpu_block_size, N)))

    # Iterate spatial blocks
    for i0 in range(0, N, cpu_block_size):
        i1 = min(N, i0 + cpu_block_size)
        for j0 in range(0, N, cpu_block_size):
            j1 = min(N, j0 + cpu_block_size)
            for k0 in range(0, N, cpu_block_size):
                k1 = min(N, k0 + cpu_block_size)

                Xb, Yb, Zb = np.meshgrid(
                    x[i0:i1], y[j0:j1], z[k0:k1], indexing="ij"
                )
                block = np.zeros(Xb.shape, dtype=np.float64)

                # Sub-batch estimation with ~600MB budget per sub-batch
                elements = Xb.size
                bytes_per_elem = 8
                est_per_particle = elements * bytes_per_elem * 6
                budget = int(600 * (1024**2))
                if est_per_particle <= 0:
                    subbatch = min(n_particles, 64)
                else:
                    subbatch = max(1, min(n_particles, budget // est_per_particle))
                    subbatch = min(subbatch, 128)

                for p0 in range(0, n_particles, subbatch):
                    p1 = min(n_particles, p0 + subbatch)
                    px = positions[p0:p1, 0]
                    py = positions[p0:p1, 1]
                    pz = positions[p0:p1, 2]
                    cq = charges[p0:p1]

                    dx = Xb[..., None] - px[None, None, None, :]
                    dy = Yb[..., None] - py[None, None, None, :]
                    dz = Zb[..., None] - pz[None, None, None, :]
                    r2 = dx * dx + dy * dy + dz * dz
                    mask = r2 < r_cut2
                    contrib = mask.astype(np.float64) * cq[None, None, None, :]
                    block += float(strength) * contrib.sum(axis=-1)

                if num_pairs:
                    block += float(strength) * int(num_pairs)
                if num_triples:
                    block += float(strength) * int(num_triples)

                result[i0:i1, j0:j1, k0:k1] = block

    return result


