"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Susceptibility exponent (γ) estimator with CUDA optimization.

This module implements block-aware estimation of susceptibility exponent γ
from block variance scaling with CUDA acceleration.

Physical Meaning:
    Estimates susceptibility exponent γ from block-wise variance scaling
    preserving 7D structure. Susceptibility χ = Var(A)/Mean(A) scales as
    χ ~ |t|^{-γ} near criticality, where t is the deviation from critical
    amplitude. Uses CUDA-accelerated vectorized block statistics with optimal
    memory management (blocks up to 80% of GPU memory). All operations respect
    7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    For each block, compute using vectorized operations:
    - χ_block = Var(A_block) / Mean(A_block) = ⟨(A - μ)²⟩ / μ
    - t_block = |Mean(A_block) - A_c|
    Fit χ ~ |t|^{-γ} using robust Theil-Sen regression with outlier suppression.
    All operations preserve 7D block structure. Block size is optimized to use
    up to 80% of GPU memory, ensuring maximum computational efficiency while
    preserving 7D locality information.

Example:
    >>> gamma = estimate_chi_from_variance(amplitude)
"""

from __future__ import annotations

from typing import List
import numpy as np
import logging

from .block_utils import iter_blocks
from .robust_fit import robust_loglog_slope
from .cuda_estimator_utils import (
    get_cuda_backend,
    compute_block_statistics_cuda,
    compute_global_mean_cuda,
    compute_optimal_block_size,
)

logger = logging.getLogger(__name__)


def estimate_chi_from_variance(amplitude: np.ndarray) -> float:
    """
    Estimate γ (susceptibility exponent) from block variance scaling with 7D structure.

    Physical Meaning:
        Estimates susceptibility exponent γ from block-wise variance scaling
        preserving 7D structure. Susceptibility χ = Var(A)/Mean(A) scales as
        χ ~ |t|^{-γ} near criticality, where t is the deviation from critical
        amplitude. Uses CUDA-accelerated vectorized block statistics with optimal
        memory management (blocks up to 80% of GPU memory). All operations respect
        7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For each block, compute using vectorized operations:
        - χ_block = Var(A_block) / Mean(A_block) = ⟨(A - μ)²⟩ / μ
        - t_block = |Mean(A_block) - A_c|
        Fit χ ~ |t|^{-γ} using robust Theil-Sen regression with outlier suppression.
        All operations preserve 7D block structure. Block size is optimized to use
        up to 80% of GPU memory, ensuring maximum computational efficiency while
        preserving 7D locality information.

    Args:
        amplitude (np.ndarray): Field amplitude (7D structure preserved).

    Returns:
        float: Susceptibility exponent γ.

    Raises:
        ValueError: If insufficient block data for robust estimation.
    """
    cuda_backend = get_cuda_backend()

    # Compute global critical amplitude using CUDA if available (vectorized)
    # This is used as reference point for control parameter t
    # Preserves 7D structure by computing mean over full 7D space-time
    if cuda_backend is not None:
        A_c = compute_global_mean_cuda(amplitude, cuda_backend)
    else:
        # CPU vectorized mean preserving 7D structure
        A_c = float(np.mean(amplitude))

    t_vals: List[float] = []
    chi_vals: List[float] = []
    total_elems = amplitude.size

    # Adaptive block size calculation based on GPU memory (80% limit)
    # For variance computation, need space for: block array + mean + variance
    min_block_elems = compute_optimal_block_size(
        amplitude,
        cuda_backend,
        memory_overhead_factor=3.0,
        min_block_elems=512,
        max_block_elems=524288,
        fraction_of_total=0.0015,
    )

    block_count = 0
    # Process blocks preserving 7D structure
    # Block-aware processing: process coherent blocks from iter_blocks
    # preserving 7D locality information M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    for block in iter_blocks(amplitude):
        block_arr = amplitude[block]
        if block_arr.size < min_block_elems:
            continue

        # Compute block statistics using CUDA-accelerated vectorized operations
        # Preserves 7D block structure by computing statistics on coherent blocks
        # All operations are fully vectorized and respect 7D structure
        if cuda_backend is not None:
            m, v = compute_block_statistics_cuda(block_arr, cuda_backend)
        else:
            # CPU vectorized mean and variance preserving 7D structure
            m = float(np.mean(block_arr))
            v = float(np.var(block_arr))

        # Validate statistics (no fixed fallbacks)
        # Must be positive and finite for meaningful susceptibility computation
        if m <= 1e-12 or not np.isfinite(m):
            continue
        if v <= 0 or not np.isfinite(v):
            continue

        # Control parameter: deviation from critical amplitude
        # t = |⟨A_block⟩ - A_c| represents distance from critical point
        # This measures how far the block is from criticality
        t = abs(m - A_c)
        if t <= 1e-12:  # Avoid numerical issues near critical point
            continue

        # Susceptibility: variance normalized by mean
        # χ = Var(A) / Mean(A) represents fluctuation-to-mean ratio
        # This characterizes the response of the system to perturbations
        chi = v / m
        if chi > 1e-12 and np.isfinite(chi):
            t_vals.append(t)
            chi_vals.append(chi)
            block_count += 1

    # Validate sufficient data for robust estimation
    # No fixed fallbacks - require minimum blocks for reliable estimate
    if len(t_vals) < 3:
        raise ValueError(
            f"insufficient block data for γ estimate: only {len(t_vals)} blocks "
            f"with valid statistics (need ≥3). "
            f"Total elements: {total_elems}, min block size: {min_block_elems}, "
            f"blocks processed: {block_count}"
        )

    # Robust log-log fit using Theil-Sen with outlier suppression
    # No fixed fallbacks - raises ValueError if fit fails
    # Theil-Sen provides 50% breakdown point and is computationally efficient
    t_array = np.asarray(t_vals)
    chi_array = np.asarray(chi_vals)
    slope = robust_loglog_slope(t_array, chi_array, method="theil_sen")
    gamma = -slope

    # Validate result (no fixed fallback)
    if not np.isfinite(gamma):
        raise ValueError(
            f"computed γ is not finite: {gamma} from {len(t_vals)} blocks. "
            f"t range: [{np.min(t_array):.2e}, {np.max(t_array):.2e}], "
            f"χ range: [{np.min(chi_array):.2e}, {np.max(chi_array):.2e}]"
        )

    logger.info(
        f"Estimated γ={gamma:.4f} from {block_count} blocks "
        f"(t range: [{np.min(t_array):.2e}, {np.max(t_array):.2e}], "
        f"χ range: [{np.min(chi_array):.2e}, {np.max(chi_array):.2e}])"
    )

    return float(gamma)

