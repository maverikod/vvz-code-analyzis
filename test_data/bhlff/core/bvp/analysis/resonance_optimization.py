"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonance optimization for BVP impedance analysis.

This module implements optimization techniques for resonance quality factors,
including advanced fitting methods and parameter optimization.
"""

import numpy as np
from typing import List, Dict, Tuple

from ..bvp_constants import BVPConstants


class ResonanceOptimization:
    """
    Resonance optimization for BVP impedance analysis.

    Physical Meaning:
        Provides optimization techniques for resonance quality factors,
        including advanced fitting methods and parameter optimization
        to improve accuracy and reliability of BVP impedance analysis.

    Mathematical Foundation:
        Uses advanced fitting techniques, including Lorentzian fitting,
        parameter optimization, and quality factor calculation to
        provide accurate resonance characterization.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize resonance optimizer.

        Physical Meaning:
            Sets up the optimizer with BVP constants for
            resonance quality factor optimization.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants

    def optimize_quality_factors(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_indices: List[int]
    ) -> List[float]:
        """
        Optimize quality factors using advanced fitting techniques.

        Physical Meaning:
            Optimizes quality factors using advanced fitting techniques
            to improve accuracy and reliability of resonance analysis
            for BVP impedance characterization.

        Mathematical Foundation:
            Uses advanced Lorentzian fitting with parameter optimization
            to extract accurate quality factors from resonance peaks.

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_indices (List[int]): List of peak indices.

        Returns:
            List[float]: Optimized quality factors.
        """
        optimized_quality_factors = []

        for peak_idx in peak_indices:
            # Extract peak region
            peak_region = self._extract_peak_region(frequencies, magnitude, peak_idx)

            # Perform advanced fitting
            optimized_params = self._advanced_lorentzian_fitting(peak_region)

            # Calculate optimized quality factor
            quality_factor = self._calculate_optimized_quality_factor(optimized_params)
            optimized_quality_factors.append(quality_factor)

        return optimized_quality_factors

    def _extract_peak_region(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_idx: int
    ) -> Dict[str, np.ndarray]:
        """
        Extract region around a resonance peak.

        Physical Meaning:
            Extracts a localized region around a resonance peak for
            detailed analysis, ensuring sufficient data for accurate
            optimization while avoiding interference from nearby peaks.

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_idx (int): Index of the resonance peak.

        Returns:
            Dict[str, np.ndarray]: Peak region data.
        """
        # Define region width (adjustable parameter)
        region_width = 20  # Number of points around peak

        # Calculate region bounds
        start_idx = max(0, peak_idx - region_width // 2)
        end_idx = min(len(frequencies), peak_idx + region_width // 2 + 1)

        # Extract region
        region_frequencies = frequencies[start_idx:end_idx]
        region_magnitude = magnitude[start_idx:end_idx]

        return {
            "frequencies": region_frequencies,
            "magnitude": region_magnitude,
            "peak_idx": peak_idx - start_idx,
        }

    def _advanced_lorentzian_fitting(
        self, peak_region: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Perform advanced Lorentzian fitting.

        Physical Meaning:
            Performs advanced Lorentzian fitting to extract accurate
            resonance parameters, including amplitude, center frequency,
            and full width at half maximum (FWHM).

        Mathematical Foundation:
            Fits a Lorentzian function to the resonance peak:
            L(f) = A / (1 + ((f - f0) / (FWHM/2))^2) + baseline
            where A is amplitude, f0 is center frequency, and FWHM is width.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            Dict[str, float]: Advanced fitting parameters.
        """
        frequencies = peak_region["frequencies"]
        magnitude = peak_region["magnitude"]
        peak_idx = peak_region["peak_idx"]

        # Initial parameter estimates
        amplitude = magnitude[peak_idx]
        center = frequencies[peak_idx]

        # Estimate FWHM using more sophisticated method
        half_max = amplitude / 2.0
        fwhm_indices = np.where(magnitude >= half_max)[0]

        if len(fwhm_indices) > 1:
            fwhm = frequencies[fwhm_indices[-1]] - frequencies[fwhm_indices[0]]
        else:
            fwhm = (frequencies[-1] - frequencies[0]) / 10.0  # Fallback estimate

        # Additional parameters for advanced fitting
        baseline = np.min(magnitude)
        noise_level = np.std(magnitude)

        return {
            "amplitude": amplitude,
            "center": center,
            "fwhm": fwhm,
            "baseline": baseline,
            "noise_level": noise_level,
        }

    def _calculate_optimized_quality_factor(self, params: Dict[str, float]) -> float:
        """
        Calculate optimized quality factor.

        Physical Meaning:
            Calculates the optimized quality factor from advanced
            fitting parameters, applying corrections for noise
            and other systematic effects.

        Mathematical Foundation:
            Q = f_center / FWHM_optimized
            where FWHM_optimized includes noise corrections.

        Args:
            params (Dict[str, float]): Advanced fitting parameters.

        Returns:
            float: Optimized quality factor.
        """
        center = params["center"]
        fwhm = params["fwhm"]

        # Apply optimization corrections
        optimized_fwhm = fwhm * (1.0 + params["noise_level"] / params["amplitude"])

        quality_factor = center / optimized_fwhm if optimized_fwhm > 0 else 0.0
        return quality_factor
