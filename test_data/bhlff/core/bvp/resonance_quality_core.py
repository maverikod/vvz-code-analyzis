"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core resonance quality factor analysis for BVP impedance analysis.

This module implements core algorithms for calculating quality factors
of resonance peaks using Lorentzian fitting and FWHM analysis.
"""

import numpy as np
from typing import List, Dict

from .bvp_constants import BVPConstants


class ResonanceQualityCore:
    """
    Core quality factor analysis for resonance peaks.

    Physical Meaning:
        Calculates quality factors of resonance peaks using
        Lorentzian fitting and FWHM analysis.
    """

    def __init__(self, constants: BVPConstants):
        """
        Initialize quality analyzer.

        Args:
            constants (BVPConstants): BVP constants instance.
        """
        self.constants = constants

    def calculate_quality_factors(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_indices: List[int]
    ) -> List[float]:
        """
        Calculate quality factors for multiple resonance peaks.

        Physical Meaning:
            Calculates quality factors for multiple resonance peaks
            using Lorentzian fitting and FWHM analysis.

        Mathematical Foundation:
            Q = f₀ / Δf where f₀ is the resonance frequency and
            Δf is the full width at half maximum (FWHM).

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_indices (List[int]): List of peak indices.

        Returns:
            List[float]: List of quality factors for each peak.
        """
        quality_factors = []

        for peak_idx in peak_indices:
            q_factor = self.calculate_quality_factor(frequencies, magnitude, peak_idx)
            quality_factors.append(q_factor)

        return quality_factors

    def calculate_quality_factor(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_idx: int
    ) -> float:
        """
        Calculate quality factor for a single resonance peak.

        Physical Meaning:
            Calculates quality factor for a single resonance peak
            using Lorentzian fitting and FWHM analysis.

        Mathematical Foundation:
            Q = f₀ / Δf where f₀ is the resonance frequency and
            Δf is the full width at half maximum (FWHM).

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_idx (int): Index of the resonance peak.

        Returns:
            float: Quality factor for the peak.
        """
        # Extract peak region
        peak_region = self._extract_peak_region(frequencies, magnitude, peak_idx)

        # Fit Lorentzian function
        lorentzian_params = self._fit_lorentzian(peak_region)

        # Calculate FWHM
        fwhm = self._calculate_fwhm(lorentzian_params)

        # Calculate quality factor
        resonance_frequency = lorentzian_params["center"]
        quality_factor = resonance_frequency / fwhm if fwhm > 0 else 0.0

        return quality_factor

    def analyze_resonance_quality(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_indices: List[int]
    ) -> Dict[str, any]:
        """
        Analyze resonance quality for multiple peaks.

        Physical Meaning:
            Performs comprehensive analysis of resonance quality
            for multiple peaks, including quality factors, FWHM,
            and resonance characteristics.

        Args:
            frequencies (np.ndarray): Frequency array.
            magnitude (np.ndarray): Magnitude response array.
            peak_indices (List[int]): List of peak indices.

        Returns:
            Dict[str, any]: Analysis results including quality factors,
                FWHM values, and resonance characteristics.
        """
        analysis_results = {
            "quality_factors": [],
            "fwhm_values": [],
            "resonance_frequencies": [],
            "peak_amplitudes": [],
            "lorentzian_params": [],
        }

        for peak_idx in peak_indices:
            # Calculate quality factor
            q_factor = self.calculate_quality_factor(frequencies, magnitude, peak_idx)
            analysis_results["quality_factors"].append(q_factor)

            # Extract peak region
            peak_region = self._extract_peak_region(frequencies, magnitude, peak_idx)

            # Fit Lorentzian function
            lorentzian_params = self._fit_lorentzian(peak_region)
            analysis_results["lorentzian_params"].append(lorentzian_params)

            # Calculate FWHM
            fwhm = self._calculate_fwhm(lorentzian_params)
            analysis_results["fwhm_values"].append(fwhm)

            # Store resonance characteristics
            analysis_results["resonance_frequencies"].append(
                lorentzian_params["center"]
            )
            analysis_results["peak_amplitudes"].append(lorentzian_params["amplitude"])

        return analysis_results

    def _extract_peak_region(
        self, frequencies: np.ndarray, magnitude: np.ndarray, peak_idx: int
    ) -> Dict[str, np.ndarray]:
        """
        Extract region around a resonance peak.

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

    def _fit_lorentzian(self, peak_region: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Fit Lorentzian function to peak region.

        Mathematical Foundation:
            Lorentzian function: L(f) = A / (1 + ((f - f₀) / (Δf/2))²)
            where A is amplitude, f₀ is center frequency, and Δf is FWHM.

        Args:
            peak_region (Dict[str, np.ndarray]): Peak region data.

        Returns:
            Dict[str, float]: Lorentzian parameters.
        """
        frequencies = peak_region["frequencies"]
        magnitude = peak_region["magnitude"]
        peak_idx = peak_region["peak_idx"]

        # Initial parameter estimates
        amplitude = magnitude[peak_idx]
        center = frequencies[peak_idx]

        # Estimate FWHM from data
        half_max = amplitude / 2.0
        fwhm_indices = np.where(magnitude >= half_max)[0]

        if len(fwhm_indices) > 1:
            fwhm = frequencies[fwhm_indices[-1]] - frequencies[fwhm_indices[0]]
        else:
            fwhm = (frequencies[-1] - frequencies[0]) / 10.0  # Fallback estimate

        return {"amplitude": amplitude, "center": center, "fwhm": fwhm}

    def _calculate_fwhm(self, lorentzian_params: Dict[str, float]) -> float:
        """
        Calculate full width at half maximum from Lorentzian parameters.

        Args:
            lorentzian_params (Dict[str, float]): Lorentzian parameters.

        Returns:
            float: FWHM value.
        """
        return lorentzian_params["fwhm"]

    def validate_quality_factor(self, quality_factor: float) -> bool:
        """
        Validate quality factor value.

        Args:
            quality_factor (float): Quality factor to validate.

        Returns:
            bool: True if quality factor is valid, False otherwise.
        """
        # Quality factor should be positive and finite
        return np.isfinite(quality_factor) and quality_factor > 0.0

    def calculate_quality_factor_statistics(
        self, quality_factors: List[float]
    ) -> Dict[str, float]:
        """
        Calculate statistics for quality factors.

        Args:
            quality_factors (List[float]): List of quality factors.

        Returns:
            Dict[str, float]: Quality factor statistics.
        """
        if not quality_factors:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "count": 0}

        quality_factors_array = np.array(quality_factors)

        return {
            "mean": np.mean(quality_factors_array),
            "std": np.std(quality_factors_array),
            "min": np.min(quality_factors_array),
            "max": np.max(quality_factors_array),
            "count": len(quality_factors),
        }
