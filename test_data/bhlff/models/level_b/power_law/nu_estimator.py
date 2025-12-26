"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Correlation length exponent (ν) estimator with CUDA optimization.

This module implements block-aware estimation of correlation length exponent ν
from block-wise correlation length scaling with CUDA acceleration.

Physical Meaning:
    Estimates correlation length exponent ν from block-wise correlation
    length scaling. Preserves 7D structure by computing correlations
    within blocks using CUDA-accelerated 7D FFT operations. Uses block-aware
    sampling with optimal GPU memory management (blocks up to 80% of available memory).
    All operations are fully vectorized and respect 7D space-time structure
    M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    For each block, compute correlation length ξ_block and control
    parameter t_block = |⟨A_block⟩ - A_c|. Fit ξ ~ |t|^{-ν} using
    robust Theil-Sen regression with outlier suppression. Correlation
    function computed via 7D FFT: C(r) = FFT⁻¹[|FFT[a]|²] preserving
    full 7D structure. Block size is optimized to use up to 80% of GPU
    memory, ensuring maximum computational efficiency while preserving
    7D locality information.

Example:
    >>> nu = estimate_nu_from_correlation_length(bvp_core, amplitude)
"""

from __future__ import annotations

from typing import Any, List
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


def estimate_nu_from_correlation_length(bvp_core: Any, amplitude: np.ndarray) -> float:
    """
    Estimate ν via block-aware scaling of correlation length: ξ ~ |t|^{-ν}.

    Physical Meaning:
        Estimates correlation length exponent ν from block-wise correlation
        length scaling. Preserves 7D structure by computing correlations
        within blocks using CUDA-accelerated 7D FFT operations. Uses block-aware
        sampling with optimal GPU memory management (blocks up to 80% of available memory).
        All operations are fully vectorized and respect 7D space-time structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For each block, compute correlation length ξ_block and control
        parameter t_block = |⟨A_block⟩ - A_c|. Fit ξ ~ |t|^{-ν} using
        robust Theil-Sen regression with outlier suppression. Correlation
        function computed via 7D FFT: C(r) = FFT⁻¹[|FFT[a]|²] preserving
        full 7D structure. Block size is optimized to use up to 80% of GPU
        memory, ensuring maximum computational efficiency while preserving
        7D locality information.

    Args:
        bvp_core (Any): BVP core instance for correlation computation.
        amplitude (np.ndarray): Field amplitude (7D structure preserved).

    Returns:
        float: Correlation length exponent ν.

    Raises:
        ValueError: If insufficient block data for robust estimation.
    """
    from .correlation_analysis import CorrelationAnalysis

    # Compute global critical amplitude using CUDA if available (vectorized)
    cuda_backend = get_cuda_backend()
    if cuda_backend is not None:
        A_c = compute_global_mean_cuda(amplitude, cuda_backend)
    else:
        # CPU vectorized mean preserving 7D structure
        A_c = float(np.mean(amplitude))

    corr = CorrelationAnalysis(bvp_core)
    t_vals: List[float] = []
    xi_vals: List[float] = []
    total_elems = amplitude.size

    # Adaptive block size calculation based on GPU memory (80% limit)
    # For 7D correlation FFT, need ~4x memory overhead
    min_block_elems = compute_optimal_block_size(
        amplitude,
        cuda_backend,
        memory_overhead_factor=4.0,
        min_block_elems=512,
        max_block_elems=1048576,
        fraction_of_total=0.001,
    )

    block_count = 0
    for block in iter_blocks(amplitude):
        block_arr = amplitude[block]
        if block_arr.size < min_block_elems:
            continue

        # Compute block mean using CUDA if available (fully vectorized)
        # Preserves 7D structure by computing statistics on coherent blocks
        if cuda_backend is not None:
            A_b, _ = compute_block_statistics_cuda(block_arr, cuda_backend)
        else:
            # CPU vectorized mean preserving 7D structure
            A_b = float(np.mean(block_arr))

        # Control parameter: deviation from critical amplitude
        t = abs(A_b - A_c)
        if t <= 1e-12:  # Avoid numerical issues near critical point
            continue

        try:
            # Compute 7D correlation function preserving full block structure
            # Uses CUDA-accelerated 7D FFT if available, fully vectorized
            # This maintains 7D locality by computing correlations within
            # coherent blocks from iter_blocks, preserving M₇ structure
            c7 = corr._compute_7d_correlation_function(block_arr)
            lens = corr._compute_7d_correlation_lengths(c7)
            if not lens:
                continue

            # Average correlation length across all 7 dimensions
            # This preserves 7D structure by averaging over all spatial (ℝ³ₓ),
            # phase (𝕋³_φ), and temporal (ℝₜ) dimensions
            xi_values = np.array(list(lens.values()))
            xi = float(np.mean(xi_values))

            # Validate correlation length (must be positive and finite)
            if xi > 1e-12 and np.isfinite(xi):
                t_vals.append(t)
                xi_vals.append(xi)
                block_count += 1
        except Exception as e:
            logger.debug(f"Correlation computation failed for block: {e}")
            continue

    # Validate sufficient data for robust estimation
    # No fixed fallbacks - require minimum blocks for reliable estimate
    if len(t_vals) < 3:
        raise ValueError(
            f"insufficient block data for ν estimate: only {len(t_vals)} blocks "
            f"with valid correlations (need ≥3). "
            f"Total elements: {total_elems}, min block size: {min_block_elems}, "
            f"blocks processed: {block_count}"
        )

    # Robust log-log fit using Theil-Sen with outlier suppression
    # No fixed fallbacks - raises ValueError if fit fails
    # Theil-Sen provides 50% breakdown point and is computationally efficient
    t_array = np.asarray(t_vals)
    xi_array = np.asarray(xi_vals)
    slope = robust_loglog_slope(t_array, xi_array, method="theil_sen")
    nu = -slope

    # Validate result (no fixed fallback)
    if not np.isfinite(nu):
        raise ValueError(
            f"computed ν is not finite: {nu} from {len(t_vals)} blocks. "
            f"t range: [{np.min(t_array):.2e}, {np.max(t_array):.2e}], "
            f"ξ range: [{np.min(xi_array):.2e}, {np.max(xi_array):.2e}]"
        )

    logger.info(
        f"Estimated ν={nu:.4f} from {block_count} blocks "
        f"(t range: [{np.min(t_array):.2e}, {np.max(t_array):.2e}], "
        f"ξ range: [{np.min(xi_array):.2e}, {np.max(xi_array):.2e}])"
    )

    return float(nu)

