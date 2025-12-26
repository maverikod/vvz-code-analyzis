"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law tail analysis for stepwise power law analysis.

This module implements methods for analyzing classical power-law tail
behavior A(r) ∝ r^(2β-3) in phase fields.

Theoretical Background:
    In spectral form: â = ŝ / (μ|k|^(2β)+λ). For λ≈0 the real-space tail
    is algebraic with slope 2β-3 in 3D, representing fundamental decay
    behavior of fractional Laplacian solutions.

Example:
    >>> analyzer = PowerLawTailAnalyzer()
    >>> result = analyzer.analyze(field, beta, center)
"""

import numpy as np
from typing import Dict, Any, List
from scipy import stats


class PowerLawTailAnalyzer:
    """
    Power law tail analysis for phase fields.

    Physical Meaning:
        Analyzes algebraic decay in the tail region consistent with
        the fractional Laplacian symbol, validating theoretical predictions.

    Mathematical Foundation:
        Validates that A(r) ∝ r^(2β-3) in the tail region through
        log-log regression and comparison with theoretical slope.
    """

    def __init__(self, eps: float = 1e-15):
        """
        Initialize power law tail analyzer.

        Physical Meaning:
            Sets up analyzer with numerical stability parameters for
            computing power law fits and validating theoretical predictions.

        Args:
            eps (float): Numerical stability epsilon.
        """
        self.eps = eps

    def analyze(
        self,
        field: np.ndarray,
        beta: float,
        center: List[float],
        radial_profile: Dict[str, np.ndarray],
        min_decades: float = 1.0,
        r_min: float = None,
    ) -> Dict[str, Any]:
        """
        Analyze classical power-law tail A(r) ∝ r^(2β-3) on the field.

        Physical Meaning:
            Validates that the phase field exhibits algebraic decay in the tail
            region consistent with the fractional Laplacian symbol.

        Mathematical Foundation:
            In spectral form: â = ŝ / (μ|k|^(2β)+λ). For λ≈0 the real-space tail
            is algebraic with slope 2β-3 in 3D.

        Args:
            field (np.ndarray): Phase field solution.
            beta (float): Fractional order β ∈ (0,2).
            center (List[float]): Center coordinates [x, y, z].
            radial_profile (Dict[str, np.ndarray]): Pre-computed radial profile.
            min_decades (float): Minimum dynamic range in decades.
            r_min (float, optional): Minimum radius for tail analysis. If None,
                uses 2.0 * r_core.

        Returns:
            Dict[str, Any]: Fit metrics and data for plotting including:
                - slope: Fitted power law slope
                - slope_ci_95: 95% confidence interval for slope (tuple)
                - decades: Number of decades in the fit range
                - r_squared: R-squared value of the fit
                - passed: Whether all criteria are met
        """
        r = radial_profile["r"]
        A = radial_profile["A"]

        # Determine tail region
        if r_min is not None:
            mask_tail = r >= r_min
        else:
            r_core = self._estimate_core_radius(radial_profile)
            mask_tail = r > max(2.0 * r_core, 1e-9)
        
        r_tail = r[mask_tail]
        A_tail = np.abs(A[mask_tail])

        valid = (A_tail > self.eps) & np.isfinite(A_tail) & (r_tail > self.eps)
        r_tail = r_tail[valid]
        A_tail = A_tail[valid]

        if len(r_tail) < 5:
            return {
                "passed": False,
                "error": "Insufficient tail samples",
                "radial_profile": radial_profile,
                "tail_data": {"log_r": np.array([]), "log_A": np.array([])},
                "slope": 0.0,
                "slope_ci_95": (0.0, 0.0),
                "decades": 0.0,
                "r_squared": 0.0,
            }

        # Filter out values that would cause underflow in log
        # Use eps to avoid log(0) and log(very small values)
        min_r = max(r_tail.min(), self.eps)
        min_A = max(A_tail.min(), self.eps)
        
        # Clip values to avoid underflow
        r_tail = np.clip(r_tail, min_r, None)
        A_tail = np.clip(A_tail, min_A, None)
        
        log_r = np.log(r_tail)
        log_A = np.log(A_tail)

        # Compute number of decades
        decades = float(np.log10(r_tail.max() / max(r_tail.min(), self.eps)))

        # Linear regression with confidence interval
        slope, intercept, r_value, p_value, std_err = stats.linregress(log_r, log_A)
        r_squared = float(r_value**2)
        theoretical_slope = float(2.0 * beta - 3.0)
        
        # Compute 95% confidence interval for slope
        # Using t-distribution with n-2 degrees of freedom
        n = len(log_r)
        if n > 2:
            from scipy.stats import t
            t_critical = t.ppf(0.975, n - 2)  # 95% CI, two-tailed
            slope_ci_95 = (
                float(slope - t_critical * std_err),
                float(slope + t_critical * std_err),
            )
        else:
            slope_ci_95 = (float(slope), float(slope))
        
        rel_err = abs(slope - theoretical_slope) / max(abs(theoretical_slope), self.eps)

        # Check all criteria from document 7d-32
        passed = (
            (r_squared >= 0.99) and 
            (decades >= min_decades) and
            (slope_ci_95[0] <= theoretical_slope + 0.05) and
            (slope_ci_95[1] >= theoretical_slope - 0.05)
        )

        return {
            "slope": float(slope),
            "intercept": float(intercept),
            "theoretical_slope": theoretical_slope,
            "relative_error": float(rel_err),
            "r_squared": r_squared,
            "decades": decades,
            "log_range": decades,  # Backward compatibility
            "slope_ci_95": slope_ci_95,
            "passed": passed,
            "radial_profile": radial_profile,
            "tail_data": {"log_r": log_r, "log_A": log_A},
        }

    def _estimate_core_radius(self, radial_profile: Dict[str, np.ndarray]) -> float:
        """
        Estimate core radius from radial profile.

        Physical Meaning:
            Estimates the radius of the core region where the field
            amplitude is highest and most coherent.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.

        Returns:
            float: Estimated core radius.
        """
        A = radial_profile["A"]
        r = radial_profile["r"]

        max_idx = np.argmax(A)
        max_amplitude = A[max_idx]

        threshold = 0.5 * max_amplitude
        below_threshold = A < threshold

        if np.any(below_threshold):
            core_idx = np.where(below_threshold)[0]
            if len(core_idx) > 0:
                return r[core_idx[0]]

        return 0.05 * r.max()
