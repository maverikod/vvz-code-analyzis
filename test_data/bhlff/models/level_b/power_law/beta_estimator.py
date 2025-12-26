"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Order parameter exponent (β) estimator with CUDA optimization.

This module implements block-aware estimation of order parameter exponent β
from CCDF tail analysis with CUDA acceleration.

Physical Meaning:
    Estimates order parameter exponent β from the tail of the complementary
    cumulative distribution function (CCDF). Preserves 7D block structure by
    computing CCDF per block using block-aware sampling and aggregating,
    avoiding global flattening that loses 7D locality information. Uses
    CUDA-accelerated vectorized operations with optimal memory management
    (blocks up to 80% of GPU memory). All operations respect 7D space-time
    structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    For power-law tail: CCDF(A) = P(>A) ~ A^{-β}
    Computes CCDF per block on common amplitude grid using vectorized
    broadcasting: P(>A) = (1/N) Σᵢ I(Aᵢ > A) where I is indicator function.
    Then averages across blocks and fits log(CCDF) ~ -β log(A) using
    robust Theil-Sen regression with outlier suppression. Block size is
    optimized to use up to 80% of GPU memory, ensuring maximum efficiency
    while preserving 7D locality.

Example:
    >>> beta = estimate_beta_from_tail(amplitude)
"""

from __future__ import annotations

from typing import List
import numpy as np
import logging

from .block_utils import iter_blocks
from .robust_fit import robust_loglog_slope
from .cuda_estimator_utils import (
    get_cuda_backend,
    compute_ccdf_cuda,
    compute_optimal_block_size,
)

logger = logging.getLogger(__name__)


def estimate_beta_from_tail(amplitude: np.ndarray) -> float:
    """
    Estimate β from the tail CCDF across blocks preserving 7D block structure.

    Physical Meaning:
        Estimates order parameter exponent β from the tail of the complementary
        cumulative distribution function (CCDF). Preserves 7D block structure by
        computing CCDF per block using block-aware sampling and aggregating,
        avoiding global flattening that loses 7D locality information. Uses
        CUDA-accelerated vectorized operations with optimal memory management
        (blocks up to 80% of GPU memory). All operations respect 7D space-time
        structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For power-law tail: CCDF(A) = P(>A) ~ A^{-β}
        Computes CCDF per block on common amplitude grid using vectorized
        broadcasting: P(>A) = (1/N) Σᵢ I(Aᵢ > A) where I is indicator function.
        Then averages across blocks and fits log(CCDF) ~ -β log(A) using
        robust Theil-Sen regression with outlier suppression. Block size is
        optimized to use up to 80% of GPU memory, ensuring maximum efficiency
        while preserving 7D locality.

    Args:
        amplitude (np.ndarray): Field amplitude (7D structure preserved).

    Returns:
        float: Order parameter exponent β.

    Raises:
        ValueError: If insufficient block data for robust estimation.
    """
    cuda_backend = get_cuda_backend()
    tail_grids: List[np.ndarray] = []
    per_block_ccdf: List[np.ndarray] = []
    total_elems = amplitude.size

    # Adaptive block size calculation based on GPU memory (80% limit)
    # For CCDF computation, need space for: block array + grid + comparison matrix
    min_block_elems = compute_optimal_block_size(
        amplitude,
        cuda_backend,
        memory_overhead_factor=2.0,
        min_block_elems=256,
        max_block_elems=1048576,
        fraction_of_total=0.002,
    )

    # First pass: determine common amplitude grid from block tails
    # This preserves block structure by analyzing tails per block
    # Block-aware processing: process coherent blocks from iter_blocks
    # preserving 7D locality information M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    for block in iter_blocks(amplitude):
        block_arr = amplitude[block]
        if block_arr.size < min_block_elems:
            continue

        # Block-aware processing: preserve 7D structure for statistics
        # Only reshape for percentile computation within block, preserving
        # 7D locality by working on coherent blocks from iter_blocks
        # This maintains block structure information while enabling
        # efficient percentile computation
        # Use reshape(-1) only for percentile stats, not global flattening
        block_reshaped = block_arr.reshape(-1)  # Local reshape for stats only
        block_filtered = block_reshaped[
            np.isfinite(block_reshaped) & (block_reshaped > 0)
        ]

        if block_filtered.size < min_block_elems:
            continue

        # Adaptive percentile range based on block size
        # Use larger tail range for larger blocks to capture power-law behavior
        # Vectorized percentile computation
        hi_adj = max(99.0, 100.0 - 100.0 / max(3.0, np.sqrt(block_filtered.size)))
        q_lo = float(np.percentile(block_filtered, 80.0))
        q_hi = float(np.percentile(block_filtered, hi_adj))

        if not np.isfinite(q_lo) or not np.isfinite(q_hi) or q_hi <= q_lo:
            continue

        # Adaptive grid size based on block statistics
        # Use more grid points for larger blocks to capture tail behavior
        n_grid = int(np.clip(np.sqrt(block_filtered.size), 12, 128))
        grid = np.linspace(q_lo, q_hi, n_grid)
        tail_grids.append(grid)

    if not tail_grids:
        raise ValueError(
            f"insufficient block data for β estimate: no valid blocks. "
            f"Total elements: {total_elems}, min block size: {min_block_elems}"
        )

    # Compute common grid as median of block grids
    # This ensures grid captures tail behavior across all blocks
    # Vectorized grid alignment
    if len(tail_grids) == 1:
        grid = tail_grids[0]
    else:
        # Align grids to common size using median
        min_size = min(len(g) for g in tail_grids)
        aligned_grids = [g[:min_size] if len(g) > min_size else g for g in tail_grids]
        grid = np.median(np.vstack(aligned_grids), axis=0)
        grid = np.unique(np.round(grid, 12))

    if grid.size < 6:
        raise ValueError(
            f"insufficient tail grid for β estimate: only {grid.size} points (need ≥6). "
            f"Number of blocks: {len(tail_grids)}"
        )

    # Second pass: compute CCDF per block on common grid using vectorized operations
    # Preserves 7D block structure by processing coherent blocks from iter_blocks
    # All operations are fully vectorized and respect 7D structure
    for block in iter_blocks(amplitude):
        block_arr = amplitude[block]
        # Block-aware processing: reshape only for CCDF computation
        # Preserves 7D locality by working on coherent blocks from iter_blocks
        # This maintains block structure information for accurate β estimation
        # Use reshape(-1) only for CCDF computation, not global flattening
        block_reshaped = block_arr.reshape(-1)  # Local reshape for CCDF only
        block_filtered = block_reshaped[
            np.isfinite(block_reshaped) & (block_reshaped > 0)
        ]

        if block_filtered.size < min_block_elems:
            continue

        # Compute CCDF using CUDA-accelerated vectorized operations if available
        # Uses broadcasting: v[None, :] > g[:, None] creates comparison matrix
        # Fully vectorized operation preserving 7D block structure
        if cuda_backend is not None:
            ccdf = compute_ccdf_cuda(block_filtered, grid, cuda_backend)
        else:
            # CPU version with vectorized broadcasting
            # Broadcasting creates efficient comparison matrix
            v = block_filtered[None, :]  # Shape: (1, block_size)
            g = grid[:, None]  # Shape: (grid_size, 1)
            # Vectorized comparison and reduction
            ccdf = (v > g).mean(axis=1)  # Shape: (grid_size,)

        # Filter valid CCDF values (positive and finite)
        # Vectorized filtering
        mask = (ccdf > 0) & np.isfinite(ccdf)
        if np.any(mask):
            per_block_ccdf.append(ccdf)

    if len(per_block_ccdf) < 2:
        raise ValueError(
            f"insufficient CCDF blocks for β estimate: only {len(per_block_ccdf)} blocks "
            f"with valid CCDF (need ≥2). Total blocks processed: {len(tail_grids)}"
        )

    # Average CCDF across blocks using vectorized operations
    # This aggregates block-wise CCDF while preserving 7D structure
    # Fully vectorized aggregation
    mean_ccdf = np.mean(np.vstack(per_block_ccdf), axis=0)

    # Robust log-log fit using Theil-Sen with outlier suppression
    # No fixed fallbacks - raises ValueError if fit fails
    # Theil-Sen provides 50% breakdown point and is computationally efficient
    slope = robust_loglog_slope(grid, mean_ccdf, method="theil_sen")
    beta = -slope

    # Validate result (no fixed fallback)
    if not np.isfinite(beta):
        raise ValueError(
            f"computed β is not finite: {beta} from {len(per_block_ccdf)} blocks. "
            f"Grid size: {grid.size}, CCDF range: [{np.min(mean_ccdf):.2e}, {np.max(mean_ccdf):.2e}]"
        )

    logger.info(
        f"Estimated β={beta:.4f} from {len(per_block_ccdf)} blocks "
        f"(grid size: {grid.size}, CCDF range: [{np.min(mean_ccdf):.2e}, {np.max(mean_ccdf):.2e}])"
    )

    return float(beta)

