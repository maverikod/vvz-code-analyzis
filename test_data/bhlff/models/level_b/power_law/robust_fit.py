"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Robust fitting utilities for power-law scaling in 7D BVP analysis.

This module provides robust log-log regression with outlier suppression
using Theil-Sen estimator and RANSAC, suitable for stable estimation of
scaling exponents in 7D BVP fields.

Physical Meaning:
    Robust exponent estimation is critical for accurate characterization
    of scaling behavior in 7D BVP fields, where heavy tails and localized
    defects introduce strong outliers and leverage points. Theil-Sen
    estimator provides high breakdown point (50%) and is computationally
    efficient for large datasets.

Mathematical Foundation:
    Theil-Sen estimator computes the median of all pairwise slopes:
    slope = median((y_j - y_i) / (x_j - x_i)) for all i < j
    This provides robustness up to 50% outliers while maintaining
    computational efficiency through vectorized operations.

Example:
    >>> slope = robust_loglog_slope(x, y)
"""

from __future__ import annotations

from typing import Optional
import numpy as np

try:
    from sklearn.linear_model import TheilSenRegressor, RANSACRegressor
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


def _theil_sen_slope_vectorized(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute Theil-Sen slope using vectorized operations for efficiency.

    Physical Meaning:
        Computes median of all pairwise slopes, providing robust
        estimation with 50% breakdown point.

    Mathematical Foundation:
        For n points, compute all n*(n-1)/2 slopes and take median.
        Uses broadcasting for efficient computation.

    Args:
        x (np.ndarray): Independent variable values.
        y (np.ndarray): Dependent variable values.

    Returns:
        float: Theil-Sen slope estimate.
    """
    n = len(x)
    if n < 2:
        raise ValueError("Need at least 2 points for Theil-Sen")

    # For large datasets, use subsampling to avoid O(n^2) memory
    if n > 1000:
        # Use random subsample of pairs
        max_pairs = 50000
        n_pairs = min(max_pairs, n * (n - 1) // 2)
        indices = np.random.choice(n, size=min(2 * max_pairs, n), replace=False)
        x_sub = x[indices]
        y_sub = y[indices]
        n_sub = len(x_sub)
    else:
        x_sub = x
        y_sub = y
        n_sub = n

    # Compute all pairwise differences
    # Use broadcasting: (x_j - x_i) for all i < j
    x_diff = x_sub[:, None] - x_sub[None, :]
    y_diff = y_sub[:, None] - y_sub[None, :]

    # Extract upper triangle (i < j)
    mask = np.triu(np.ones((n_sub, n_sub), dtype=bool), k=1)
    x_diff_flat = x_diff[mask]
    y_diff_flat = y_diff[mask]

    # Filter out zero differences
    valid = np.abs(x_diff_flat) > 1e-12
    if not np.any(valid):
        # All x values are equal - cannot compute slope
        raise ValueError(
            "All x values are equal - cannot compute robust slope. "
            "Need variation in independent variable for regression."
        )

    slopes = y_diff_flat[valid] / x_diff_flat[valid]
    slopes = slopes[np.isfinite(slopes)]

    if len(slopes) == 0:
        raise ValueError(
            "No valid slopes computed from pairwise differences. "
            "Data may be degenerate or insufficiently varied."
        )

    return float(np.median(slopes))


def robust_loglog_slope(
    x: np.ndarray, y: np.ndarray, method: str = "theil_sen"
) -> float:
    """
    Compute robust slope of log(y) vs log(x) using outlier suppression.

    Physical Meaning:
        Estimates scaling exponents from noisy, heavy-tailed data while
        suppressing outliers typical for BVP fields near criticality.
        Uses Theil-Sen estimator by default for maximum robustness.

    Mathematical Foundation:
        - Filter to positive finite pairs
        - Log-transform: log(y) vs log(x)
        - IQR-based trimming on both axes for initial outlier removal
        - Theil-Sen estimator: median of all pairwise slopes
        - Alternative: RANSAC for highly contaminated data

    Args:
        x (np.ndarray): Control parameter values (positive).
        y (np.ndarray): Measured response values (positive).
        method (str): Robust fitting method: "theil_sen" (default),
            "ransac", or "theil_sen_sklearn" (if sklearn available).

    Returns:
        float: Robust slope d log(y) / d log(x).

    Raises:
        ValueError: If insufficient data points after filtering.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size < 3:
        raise ValueError("insufficient data for robust log-log fit")

    lx = np.log(x)
    ly = np.log(y)

    # IQR-based trimming for initial outlier removal
    def _trim(v: np.ndarray) -> np.ndarray:
        q1, q3 = np.percentile(v, [25, 75])
        iqr = q3 - q1
        if iqr <= 0:
            return np.ones_like(v, dtype=bool)
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        return (v >= lo) & (v <= hi)

    m = _trim(lx) & _trim(ly)
    lx = lx[m]
    ly = ly[m]
    if lx.size < 3:
        raise ValueError("insufficient trimmed data for robust log-log fit")

    # Use robust estimator - no weak fallbacks
    if method == "theil_sen":
        slope = _theil_sen_slope_vectorized(lx, ly)
    elif method == "ransac" and SKLEARN_AVAILABLE:
        # Use RANSAC for highly contaminated data
        regressor = RANSACRegressor(
            random_state=42,
            max_trials=100,
            min_samples=0.5,
            residual_threshold=None,
        )
        regressor.fit(lx.reshape(-1, 1), ly)
        slope = float(regressor.estimator_.coef_[0])
    elif method == "theil_sen_sklearn" and SKLEARN_AVAILABLE:
        # Use sklearn's TheilSenRegressor for better numerical stability
        regressor = TheilSenRegressor(random_state=42, n_jobs=-1)
        regressor.fit(lx.reshape(-1, 1), ly)
        slope = float(regressor.coef_[0])
    elif method == "theil_sen_fallback":
        # Use quantile binning fallback (still robust, just approximate)
        slope = _theil_sen_fallback(lx, ly)
    else:
        # Default to vectorized Theil-Sen
        slope = _theil_sen_slope_vectorized(lx, ly)

    return float(slope)


def _theil_sen_fallback(x: np.ndarray, y: np.ndarray) -> float:
    """
    Robust Theil-Sen approximation using quantile binning for very large datasets.

    Physical Meaning:
        Approximates Theil-Sen by computing median slopes between
        quantile bins, providing robustness with reduced computation.
        This is still a robust method (uses median), just with reduced
        precision compared to full Theil-Sen.

    Mathematical Foundation:
        Divides data into quantile bins, computes median x and y
        within each bin, then takes median of slopes between adjacent bins.
        This preserves robustness while reducing O(n²) complexity.

    Args:
        x (np.ndarray): Independent variable values.
        y (np.ndarray): Dependent variable values.

    Returns:
        float: Approximate Theil-Sen slope (still robust).

    Raises:
        ValueError: If insufficient data for binning.
    """
    nbins = min(12, max(4, x.size // 4))
    q = np.linspace(0, 1, nbins + 1)
    bins = np.quantile(x, q)
    bins = np.unique(bins)
    if bins.size < 3:
        raise ValueError(
            f"Insufficient quantile bins for robust fallback: {bins.size} bins "
            f"from {x.size} data points. Need at least 3 bins."
        )

    binned_x = []
    binned_y = []
    for i in range(bins.size - 1):
        sel = (x >= bins[i]) & (x <= bins[i + 1])
        if np.any(sel):
            binned_x.append(np.median(x[sel]))
            binned_y.append(np.median(y[sel]))

    bx = np.asarray(binned_x)
    by = np.asarray(binned_y)
    if bx.size < 3:
        raise ValueError(
            f"Insufficient binned data points: {bx.size} (need ≥3). "
            f"Original data size: {x.size}"
        )

    # Compute median of adjacent-bin slopes (still robust)
    slopes = []
    for i in range(bx.size - 1):
        dx = bx[i + 1] - bx[i]
        if dx > 1e-12:
            slopes.append((by[i + 1] - by[i]) / dx)

    if len(slopes) == 0:
        raise ValueError(
            "No valid slopes computed from quantile bins. "
            "Data may be degenerate or insufficiently varied."
        )

    return float(np.median(slopes))
