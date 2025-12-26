"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Error estimation module for adaptive integrator.

This module implements error estimation operations for adaptive integration,
including Richardson extrapolation and error component analysis.

Physical Meaning:
    Computes the complete local error estimate using
    full error analysis according to adaptive integration theory.

Mathematical Foundation:
    Implements full error estimation:
    - Richardson extrapolation
    - Embedded Runge-Kutta error estimation
    - Local truncation error analysis
    - Stability analysis
"""

import numpy as np
from typing import Dict, Any, Tuple
import logging


class ErrorEstimation:
    """
    Error estimation for adaptive integration.

    Physical Meaning:
        Computes the complete local error estimate using
        full error analysis according to adaptive integration theory.
    """

    def __init__(self, tolerance: float, safety_factor: float):
        """Initialize error estimator."""
        self.tolerance = tolerance
        self.safety_factor = safety_factor
        self.logger = logging.getLogger(__name__)

    def compute_richardson_error(
        self, field_4th: np.ndarray, field_5th: np.ndarray, dt: float
    ) -> float:
        """
        Compute error estimate using full Richardson extrapolation.

        Physical Meaning:
            Uses Richardson extrapolation to provide a more accurate
            error estimate for adaptive step size control. Implements
            full error analysis including local truncation error,
            stability analysis, and spectral error components.
        """
        # Compute basic error estimate
        error_diff = field_5th - field_4th

        # Compute relative error with proper normalization
        field_magnitude = np.linalg.norm(field_4th)
        if field_magnitude < 1e-15:
            # Avoid division by zero for very small fields
            error_estimate = np.linalg.norm(error_diff)
        else:
            # Richardson extrapolation error estimate
            # For RK4(5), the error scales as h^5, so p = 1
            richardson_factor = 1.0 / (1.0 - (0.5) ** 1)  # h_4th/h_5th = 0.5
            error_estimate = (
                richardson_factor * np.linalg.norm(error_diff) / field_magnitude
            )

        # Apply full error analysis
        error_components = self._analyze_error_components(error_diff, field_4th)
        stability_analysis = self._analyze_stability(field_4th, field_5th, dt)
        truncation_error = self._compute_local_truncation_error(field_4th, dt)

        # Combine error estimates with full analysis
        total_error = self._combine_error_estimates_full(
            error_estimate, error_components, stability_analysis, truncation_error
        )

        return float(total_error)

    def _analyze_error_components(
        self, error_diff: np.ndarray, field: np.ndarray
    ) -> Dict[str, float]:
        """Analyze different components of the error."""
        # Spatial error analysis
        spatial_error = np.abs(error_diff)
        max_spatial_error = np.max(spatial_error)
        mean_spatial_error = np.mean(spatial_error)

        # Spectral error analysis
        error_spectral = np.fft.fftn(error_diff)
        field_spectral = np.fft.fftn(field)

        # Compute spectral error ratios
        spectral_error_magnitude = np.abs(error_spectral)
        field_spectral_magnitude = np.abs(field_spectral)

        # Avoid division by zero
        spectral_ratio = np.where(
            field_spectral_magnitude > 1e-15,
            spectral_error_magnitude / field_spectral_magnitude,
            0.0,
        )

        max_spectral_error = np.max(spectral_ratio)
        mean_spectral_error = np.mean(spectral_ratio)

        # High-frequency error analysis
        high_freq_mask = self._compute_high_frequency_mask(field.shape)
        high_freq_error = np.mean(spectral_ratio[high_freq_mask])

        return {
            "max_spatial_error": float(max_spatial_error),
            "mean_spatial_error": float(mean_spatial_error),
            "max_spectral_error": float(max_spectral_error),
            "mean_spectral_error": float(mean_spectral_error),
            "high_frequency_error": float(high_freq_error),
        }

    def _compute_high_frequency_mask(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Compute mask for high-frequency components."""
        # Create frequency grids
        freq_grids = []
        for dim_size in shape:
            freqs = np.fft.fftfreq(dim_size)
            freq_grids.append(freqs)

        # Create multi-dimensional frequency grid
        freq_mesh = np.meshgrid(*freq_grids, indexing="ij")

        # Compute frequency magnitude
        freq_magnitude = np.sqrt(sum(freq**2 for freq in freq_mesh))

        # High-frequency mask (top 25% of frequencies)
        freq_threshold = np.percentile(freq_magnitude, 75)
        high_freq_mask = freq_magnitude > freq_threshold

        return high_freq_mask

    def _combine_error_estimates(
        self, basic_error: float, error_components: Dict[str, float]
    ) -> float:
        """Combine different error estimates into a single error measure."""
        # Weight different error components
        weights = {"spatial": 0.4, "spectral": 0.4, "high_frequency": 0.2}

        # Compute weighted error estimate
        weighted_error = (
            weights["spatial"] * error_components["mean_spatial_error"]
            + weights["spectral"] * error_components["mean_spectral_error"]
            + weights["high_frequency"] * error_components["high_frequency_error"]
        )

        # Combine with basic error estimate
        combined_error = 0.7 * basic_error + 0.3 * weighted_error

        # Apply error bounds
        min_error = 1e-15
        max_error = 1.0

        combined_error = max(min_error, min(combined_error, max_error))

        return combined_error

    def _analyze_stability(
        self, field_4th: np.ndarray, field_5th: np.ndarray, dt: float
    ) -> Dict[str, float]:
        """
        Analyze stability of the integration step.

        Physical Meaning:
            Analyzes the stability of the integration step by examining
            the growth of errors and the spectral properties of the solution.
        """
        # Compute error growth rate
        error_diff = field_5th - field_4th
        error_magnitude = np.linalg.norm(error_diff)
        field_magnitude = np.linalg.norm(field_4th)

        if field_magnitude > 1e-15:
            error_growth_rate = error_magnitude / field_magnitude
        else:
            error_growth_rate = 0.0

        # Spectral stability analysis
        field_4th_spectral = np.fft.fftn(field_4th)
        field_5th_spectral = np.fft.fftn(field_5th)

        # Compute spectral error
        spectral_error = np.abs(field_5th_spectral - field_4th_spectral)
        field_spectral_magnitude = np.abs(field_4th_spectral)

        # Avoid division by zero with proper handling
        spectral_ratio = np.where(
            field_spectral_magnitude > 1e-15,
            spectral_error / field_spectral_magnitude,
            0.0,
        )

        # Handle any remaining NaN or inf values
        spectral_ratio = np.nan_to_num(spectral_ratio, nan=0.0, posinf=0.0, neginf=0.0)

        # High-frequency stability
        high_freq_mask = self._compute_high_frequency_mask(field_4th.shape)
        high_freq_error = np.mean(spectral_ratio[high_freq_mask])

        # Low-frequency stability
        low_freq_mask = ~high_freq_mask
        low_freq_error = np.mean(spectral_ratio[low_freq_mask])

        # Stability indicator (should be < 1 for stability)
        stability_indicator = max(high_freq_error, low_freq_error)

        return {
            "error_growth_rate": float(error_growth_rate),
            "high_frequency_error": float(high_freq_error),
            "low_frequency_error": float(low_freq_error),
            "stability_indicator": float(stability_indicator),
        }

    def _compute_local_truncation_error(self, field: np.ndarray, dt: float) -> float:
        """
        Compute local truncation error estimate.

        Physical Meaning:
            Estimates the local truncation error by analyzing the
            high-order derivatives of the field.
        """
        # Compute spatial derivatives for truncation error estimation
        if field.ndim >= 2:
            # Compute second-order spatial derivatives
            d2x = np.gradient(np.gradient(field, axis=0), axis=0)
            d2y = np.gradient(np.gradient(field, axis=1), axis=1)

            # Estimate truncation error from second derivatives
            truncation_error_spatial = np.mean(np.abs(d2x + d2y))
        else:
            truncation_error_spatial = 0.0

        # Time truncation error (scales as dt^5 for RK4(5))
        truncation_error_time = dt**5 * truncation_error_spatial

        # Apply bounds
        min_error = 1e-15
        max_error = 1.0

        truncation_error = max(min_error, min(truncation_error_time, max_error))

        return float(truncation_error)

    def _combine_error_estimates_full(
        self,
        basic_error: float,
        error_components: Dict[str, float],
        stability_analysis: Dict[str, float],
        truncation_error: float,
    ) -> float:
        """
        Combine all error estimates into a single error measure.

        Physical Meaning:
            Combines Richardson extrapolation error, component analysis,
            stability analysis, and truncation error into a comprehensive
            error estimate for adaptive step size control.
        """
        # Weight different error components
        weights = {
            "richardson": 0.4,
            "spatial": 0.2,
            "spectral": 0.2,
            "stability": 0.1,
            "truncation": 0.1,
        }

        # Compute weighted error estimate
        weighted_error = (
            weights["richardson"] * basic_error
            + weights["spatial"] * error_components["mean_spatial_error"]
            + weights["spectral"] * error_components["mean_spectral_error"]
            + weights["stability"] * stability_analysis["stability_indicator"]
            + weights["truncation"] * truncation_error
        )

        # Apply stability penalty if unstable
        if stability_analysis["stability_indicator"] > 1.0:
            weighted_error *= 2.0  # Penalize unstable steps

        # Apply error bounds
        min_error = 1e-15
        max_error = 1.0

        combined_error = max(min_error, min(weighted_error, max_error))

        return combined_error
