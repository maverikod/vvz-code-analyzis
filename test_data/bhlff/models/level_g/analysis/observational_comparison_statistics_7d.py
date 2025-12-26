"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D phase field statistical methods for observational comparison.

This module implements 7D phase field statistical methods for
cosmological evolution results, including correlation functions,
power spectra, and structure statistics.

Theoretical Background:
    7D phase field statistical analysis involves computing
    statistical properties from phase field evolution using
    BVP theory principles.

Mathematical Foundation:
    Implements 7D phase field statistical methods:
    - Correlation function computation
    - Power spectrum computation
    - Structure statistics computation
    - Scale analysis

Example:
    >>> stats_7d = ObservationalComparisonStatistics7D(evolution_results)
    >>> correlation = stats_7d.compute_7d_correlation_function()
"""

import numpy as np
from typing import Dict, Any


class ObservationalComparisonStatistics7D:
    """
    7D phase field statistical methods for observational comparison.

    Physical Meaning:
        Implements 7D phase field statistical methods for
        cosmological evolution results, including correlation functions,
        power spectra, and structure statistics.

    Mathematical Foundation:
        Implements 7D phase field statistical methods:
        - Correlation function computation
        - Power spectrum computation
        - Structure statistics computation
        - Scale analysis

    Attributes:
        evolution_results (dict): Cosmological evolution results
    """

    def __init__(self, evolution_results: Dict[str, Any]):
        """
        Initialize 7D statistical methods.

        Physical Meaning:
            Sets up the 7D statistical methods with evolution results.

        Args:
            evolution_results: Cosmological evolution results
        """
        self.evolution_results = evolution_results

    def compute_7d_correlation_function(self) -> np.ndarray:
        """
        Compute 7D correlation function from phase field evolution.

        Physical Meaning:
            Computes spatial correlation function from 7D phase field
            evolution results using BVP theory principles.

        Mathematical Foundation:
            ξ(r) = ⟨δ(x)δ(x+r)⟩ where δ is density contrast
            and ⟨⟩ denotes ensemble average.

        Returns:
            7D correlation function array
        """
        # Extract phase field from evolution results
        phase_field = self.evolution_results.get("phase_field", np.array([]))
        if len(phase_field) == 0:
            return np.array([])

        # Compute density contrast
        mean_density = np.mean(phase_field)
        density_contrast = (phase_field - mean_density) / mean_density

        # Compute correlation function using FFT
        from scipy.signal import correlate

        # For 3D field, compute correlation in each dimension
        if phase_field.ndim == 3:
            correlation = correlate(density_contrast, density_contrast, mode="full")
            # Normalize
            correlation = correlation / np.max(correlation)
            return correlation.flatten()
        else:
            # For 1D or 2D, use direct computation
            correlation = np.correlate(
                density_contrast.flatten(), density_contrast.flatten(), mode="full"
            )
            return correlation / np.max(correlation)

    def compute_7d_power_spectrum(self) -> np.ndarray:
        """
        Compute 7D power spectrum from phase field evolution.

        Physical Meaning:
            Computes power spectrum from 7D phase field evolution
            using BVP theory principles.

        Mathematical Foundation:
            P(k) = |δ̃(k)|² where δ̃(k) is Fourier transform
            of density contrast δ(x).

        Returns:
            7D power spectrum array
        """
        # Extract phase field from evolution results
        phase_field = self.evolution_results.get("phase_field", np.array([]))
        if len(phase_field) == 0:
            return np.array([])

        # Compute density contrast
        mean_density = np.mean(phase_field)
        density_contrast = (phase_field - mean_density) / mean_density

        # Compute power spectrum using FFT
        fft_field = np.fft.fftn(density_contrast)
        power_spectrum = np.abs(fft_field) ** 2

        # Return 1D power spectrum (radial average)
        if power_spectrum.ndim > 1:
            # Compute radial average
            kx = np.fft.fftfreq(power_spectrum.shape[0])
            ky = (
                np.fft.fftfreq(power_spectrum.shape[1])
                if power_spectrum.ndim > 1
                else np.array([0])
            )
            kz = (
                np.fft.fftfreq(power_spectrum.shape[2])
                if power_spectrum.ndim > 2
                else np.array([0])
            )

            # Create k-space grid
            if power_spectrum.ndim == 3:
                KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
                k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)
            elif power_spectrum.ndim == 2:
                KX, KY = np.meshgrid(kx, ky, indexing="ij")
                k_magnitude = np.sqrt(KX**2 + KY**2)
            else:
                k_magnitude = np.abs(kx)

            # Radial average
            k_bins = np.linspace(0, np.max(k_magnitude), 50)
            power_1d = np.zeros_like(k_bins)

            for i, k in enumerate(k_bins):
                mask = (k_magnitude >= k) & (k_magnitude < k + k_bins[1] - k_bins[0])
                if np.sum(mask) > 0:
                    power_1d[i] = np.mean(power_spectrum[mask])

            return power_1d
        else:
            return np.abs(fft_field) ** 2

    def compute_7d_structure_statistics(self) -> Dict[str, Any]:
        """
        Compute 7D structure statistics from phase field evolution.

        Physical Meaning:
            Computes statistical properties of structure formation
            from 7D phase field evolution using BVP theory.

        Mathematical Foundation:
            Computes various statistical measures:
            - Variance: σ² = ⟨δ²⟩
            - Skewness: S = ⟨δ³⟩/σ³
            - Kurtosis: K = ⟨δ⁴⟩/σ⁴ - 3

        Returns:
            Dictionary of structure statistics
        """
        # Extract phase field from evolution results
        phase_field = self.evolution_results.get("phase_field", np.array([]))
        if len(phase_field) == 0:
            return {}

        # Compute density contrast
        mean_density = np.mean(phase_field)
        density_contrast = (phase_field - mean_density) / mean_density

        # Compute basic statistics
        variance = np.var(density_contrast)
        std_dev = np.sqrt(variance)

        # Compute higher-order moments
        if std_dev > 0:
            skewness = np.mean((density_contrast / std_dev) ** 3)
            kurtosis = np.mean((density_contrast / std_dev) ** 4) - 3
        else:
            skewness = 0.0
            kurtosis = 0.0

        # Compute structure formation metrics
        structure_scale = self._compute_structure_scale(density_contrast)
        formation_time = self.evolution_results.get("formation_time", 0.0)

        statistics = {
            "variance": variance,
            "std_deviation": std_dev,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "structure_scale": structure_scale,
            "formation_time": formation_time,
            "mean_density": mean_density,
            "density_contrast_range": [
                np.min(density_contrast),
                np.max(density_contrast),
            ],
        }

        return statistics

    def _compute_structure_scale(self, density_contrast: np.ndarray) -> float:
        """
        Compute characteristic structure scale.

        Physical Meaning:
            Computes characteristic scale of structures
            from density contrast field.

        Mathematical Foundation:
            Uses correlation length as structure scale:
            ξ₀ = ∫ ξ(r) dr / ξ(0)

        Args:
            density_contrast: Density contrast field

        Returns:
            Characteristic structure scale
        """
        if density_contrast.size == 0:
            return 1.0

        # Compute correlation function
        correlation = np.correlate(
            density_contrast.flatten(), density_contrast.flatten(), mode="full"
        )
        correlation = correlation / np.max(correlation)

        # Find correlation length (where correlation drops to 1/e)
        max_corr = np.max(correlation)
        target_corr = max_corr / np.e

        # Find first point where correlation drops below target
        indices = np.where(correlation < target_corr)[0]
        if len(indices) > 0:
            correlation_length = indices[0]
        else:
            correlation_length = len(correlation) // 2

        return float(correlation_length)
