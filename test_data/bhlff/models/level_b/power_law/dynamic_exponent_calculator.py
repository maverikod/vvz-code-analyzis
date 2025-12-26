"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Dynamic exponent (z) calculator with CUDA optimization.

This module implements block-wise calculation of dynamic exponent z
from correlation time scaling with CUDA acceleration.

Physical Meaning:
    Computes dynamic exponent z from the scaling of relaxation time
    τ ~ ξ^z, where ξ is correlation length. This characterizes
    critical slowing down near the critical point. Uses block-wise
    analysis to estimate z from temporal correlation structure.

Mathematical Foundation:
    Dynamic exponent relates relaxation time to correlation length:
    τ ~ ξ^z. For BVP field, we estimate z from block-wise amplitude
    fluctuation correlations using robust regression on log-log scale.
    Estimates z from fitting log(τ) ~ z*log(ξ) across blocks.

Example:
    >>> calculator = DynamicExponentCalculator(bvp_core)
    >>> z = calculator.compute_dynamic_exponent(amplitude)
"""

from __future__ import annotations

from typing import List
import numpy as np
import logging

from bhlff.core.bvp import BVPCore
from .correlation_analysis import CorrelationAnalysis
from .robust_fit import robust_loglog_slope
from .block_utils import iter_blocks
from .cuda_estimator_utils import (
    get_cuda_backend,
    compute_block_statistics_cuda,
)

logger = logging.getLogger(__name__)


class DynamicExponentCalculator:
    """
    Dynamic exponent calculator with CUDA optimization.

    Physical Meaning:
        Computes dynamic exponent z from the scaling of relaxation time
        τ ~ ξ^z, where ξ is correlation length. Uses block-wise analysis
        with CUDA acceleration for optimal performance on large datasets.

    Mathematical Foundation:
        Dynamic exponent relates relaxation time to correlation length:
        τ ~ ξ^z. Estimates z from fitting log(τ) ~ z*log(ξ) across blocks
        using robust regression.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize dynamic exponent calculator.

        Args:
            bvp_core (BVPCore): BVP core instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def compute_dynamic_exponent(self, amplitude: np.ndarray) -> float:
        """
        Compute dynamic exponent z from block-wise correlation time scaling.

        Physical Meaning:
            Computes dynamic exponent z from the scaling of relaxation time
            τ ~ ξ^z, where ξ is correlation length. This characterizes
            critical slowing down near the critical point. Uses block-wise
            analysis to estimate z from temporal correlation structure.

        Mathematical Foundation:
            Dynamic exponent relates relaxation time to correlation length:
            τ ~ ξ^z. For BVP field, we estimate z from block-wise amplitude
            fluctuation correlations using robust regression on log-log scale.
            Estimates z from fitting log(τ) ~ z*log(ξ) across blocks.

        Args:
            amplitude (np.ndarray): Field amplitude distribution.

        Returns:
            float: Dynamic exponent z.

        Raises:
            ValueError: If insufficient block data or z is not finite.
        """
        cuda_backend = get_cuda_backend()
        correlation_analyzer = CorrelationAnalysis(self.bvp_core)

        # Block-wise estimation of z from τ ~ ξ^z
        xi_vals: List[float] = []
        tau_vals: List[float] = []
        total_elems = amplitude.size

        # Adaptive minimum block size for 7D structure
        # Uses 80% GPU memory limit with optimal block sizing
        min_block_elems = max(128, min(262144, int(0.002 * total_elems)))

        block_count = 0
        for block in iter_blocks(amplitude):
            block_arr = amplitude[block]
            if block_arr.size < min_block_elems:
                continue

            try:
                # Compute block statistics using CUDA if available
                # Fully vectorized operations preserving 7D structure
                if cuda_backend is not None:
                    mean_amp, variance = compute_block_statistics_cuda(
                        block_arr, cuda_backend
                    )
                else:
                    mean_amp = float(np.mean(block_arr))
                    variance = float(np.var(block_arr))

                # Validate statistics
                if mean_amp <= 1e-12 or not np.isfinite(mean_amp):
                    continue
                if variance <= 0 or not np.isfinite(variance):
                    continue

                # Estimate relaxation time scale from fluctuation-to-mean ratio
                # τ ~ variance / (mean^2) for diffusive systems
                tau = variance / (mean_amp**2) if mean_amp > 0 else 1.0

                # Compute correlation length for this block
                # Uses 7D correlation function preserving full structure
                corr_7d = correlation_analyzer._compute_7d_correlation_function(
                    block_arr
                )
                corr_lengths = correlation_analyzer._compute_7d_correlation_lengths(
                    corr_7d
                )

                if not corr_lengths:
                    continue

                # Average correlation length across 7 dimensions
                # Preserves 7D structure by averaging over all dimensions
                xi = float(np.mean(list(corr_lengths.values())))

                # Validate values
                if xi > 1e-12 and tau > 1e-12 and np.isfinite(xi) and np.isfinite(tau):
                    xi_vals.append(xi)
                    tau_vals.append(tau)
                    block_count += 1
            except Exception as e:
                self.logger.debug(f"Dynamic exponent computation failed for block: {e}")
                continue

        if len(xi_vals) < 3:
            raise ValueError(
                f"insufficient block data for z estimate: only {len(xi_vals)} blocks "
                f"with valid correlations (need ≥3)"
            )

        # Robust log-log fit: log(τ) ~ z*log(ξ)
        slope = robust_loglog_slope(np.asarray(xi_vals), np.asarray(tau_vals))
        z = slope

        # Validate result (no fixed fallback)
        if not np.isfinite(z):
            raise ValueError(
                f"computed z is not finite: {z} from {len(xi_vals)} blocks"
            )

        self.logger.info(
            f"Estimated z={z:.4f} from {block_count} blocks "
            f"(ξ range: [{min(xi_vals):.2e}, {max(xi_vals):.2e}], "
            f"τ range: [{min(tau_vals):.2e}, {max(tau_vals):.2e}])"
        )

        return float(z)

