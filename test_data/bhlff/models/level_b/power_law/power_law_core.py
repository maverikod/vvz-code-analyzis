"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law core analysis module for Level B.

This module implements the main power law analysis operations for Level B
of the 7D phase field theory, focusing on power law behavior and scaling.

Physical Meaning:
    Analyzes power law characteristics of the BVP field distribution,
    identifying scaling behavior, critical exponents, and correlation
    functions in the 7D space-time.

Mathematical Foundation:
    Implements power law analysis including:
    - Power law exponent computation
    - Scaling region identification
    - Correlation function analysis
    - Critical behavior analysis

Example:
    >>> core = PowerLawCore(bvp_core)
    >>> exponents = core.compute_power_law_exponents(envelope)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .correlation_analysis import CorrelationAnalysis
from .critical_exponents import CriticalExponents
from .scaling_regions import ScalingRegions


class PowerLawCore:
    """
    Core power law analysis for BVP field.

    Physical Meaning:
        Implements core power law analysis operations for identifying
        scaling behavior and critical exponents in BVP field distributions.

    Mathematical Foundation:
        Analyzes power law behavior using statistical methods including
        log-log regression, correlation analysis, and scaling region
        identification.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize power law core analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for analysis.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize specialized analyzers
        self._correlation_analyzer = CorrelationAnalysis(bvp_core)
        self._critical_exponents_analyzer = CriticalExponents(bvp_core)
        self._scaling_regions_analyzer = ScalingRegions(bvp_core)

    def compute_power_law_exponents(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Compute power law exponents from field distribution.

        Physical Meaning:
            Computes power law exponents by analyzing the amplitude
            distribution of the BVP field, identifying scaling behavior
            in the field structure.

        Mathematical Foundation:
            Uses log-log regression to fit power law distributions:
            P(x) ~ x^(-α) where α is the power law exponent.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, float]: Power law exponents including:
                - amplitude_exponent: Power law exponent for amplitude distribution
        """
        # Analyze amplitude distribution
        amplitudes = np.abs(envelope)
        amplitudes = amplitudes[amplitudes > 0]  # Remove zeros

        if len(amplitudes) == 0:
            return {
                "amplitude_exponent": 0.0,
                "r_squared": 0.0,
                "confidence_interval": (0.0, 0.0),
            }

        # Robust power law fit with R² and confidence intervals
        # Required for B1 test: R² ≥ 0.99, proper confidence intervals
        sorted_amplitudes = np.sort(amplitudes)[::-1]  # Descending order
        ranks = np.arange(1, len(sorted_amplitudes) + 1)

        # Filter out zeros and negative values
        valid_mask = sorted_amplitudes > 0
        if np.sum(valid_mask) < 3:
            return {
                "amplitude_exponent": 0.0,
                "r_squared": 0.0,
                "confidence_interval": (0.0, 0.0),
            }

        sorted_amplitudes = sorted_amplitudes[valid_mask]
        ranks = ranks[valid_mask]

        # Fit power law: P(x) ~ x^(-α) in log-log space
        log_ranks = np.log(ranks)
        log_amplitudes = np.log(sorted_amplitudes)

        # Robust linear regression with error estimation
        if len(log_ranks) > 1:
            # OLS regression
            coeffs = np.polyfit(log_ranks, log_amplitudes, 1)
            slope = coeffs[0]
            intercept = coeffs[1]
            exponent = -slope

            # Compute R² (coefficient of determination)
            y_pred = slope * log_ranks + intercept
            ss_res = np.sum((log_amplitudes - y_pred) ** 2)
            ss_tot = np.sum((log_amplitudes - np.mean(log_amplitudes)) ** 2)
            r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            # Compute confidence interval (95%) for slope
            n = len(log_ranks)
            if n > 2:
                # Standard error of slope
                se_slope = np.sqrt(ss_res / (n - 2)) / np.sqrt(
                    np.sum((log_ranks - np.mean(log_ranks)) ** 2)
                )
                # t-statistic for 95% CI (approximate, n > 30 uses ~1.96)
                t_critical = 2.0 if n < 30 else 1.96
                slope_ci = t_critical * se_slope
                # Convert to exponent CI (exponent = -slope)
                exp_ci_low = -slope - slope_ci
                exp_ci_high = -slope + slope_ci
                confidence_interval = (exp_ci_low, exp_ci_high)
            else:
                confidence_interval = (exponent, exponent)
        else:
            exponent = 0.0
            r_squared = 0.0
            confidence_interval = (0.0, 0.0)

        return {
            "amplitude_exponent": exponent,
            "r_squared": r_squared,
            "confidence_interval": confidence_interval,
        }

    def identify_scaling_regions(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Identify regions with power law scaling behavior.

        Physical Meaning:
            Identifies spatial regions where the BVP field exhibits
            power law scaling behavior, indicating critical regions
            in the field structure.

        Mathematical Foundation:
            Analyzes different spatial regions to identify consistent
            scaling behavior using power law fitting methods.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            List[Dict[str, Any]]: List of scaling regions with properties:
                - center: Center coordinates of the region
                - radius: Radius of the region
                - scaling_type: Type of scaling behavior
                - exponent: Power law exponent for the region
        """
        return self._scaling_regions_analyzer.identify_scaling_regions(envelope)

    def compute_correlation_functions(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute full 7D spatial correlation functions.

        Physical Meaning:
            Computes the complete 7D spatial correlation function
            C(r) = ⟨a(x)a(x+r)⟩ for all 7 dimensions according to
            the 7D phase field theory, preserving the full
            space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            Implements full 7D correlation analysis:
            C(r) = ∫ a(x) a*(x+r) dV_7
            where integration is over all 7D space-time M₇,
            preserving the full dimensional structure and
            computing correlation lengths in each dimension.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Full correlation analysis including:
                - spatial_correlation_7d: Full 7D correlation function
                - correlation_lengths: Correlation lengths for each dimension
                - correlation_structure: 7D correlation structure analysis
                - dimensional_correlations: Individual dimension correlations
        """
        return self._correlation_analyzer.compute_correlation_functions(envelope)

    def analyze_critical_behavior(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze critical behavior in the field.

        Physical Meaning:
            Analyzes critical behavior and phase transitions in the
            BVP field, identifying critical points and scaling behavior.

        Mathematical Foundation:
            Analyzes field properties near critical points including
            scaling exponents and critical behavior indicators.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Critical behavior analysis including:
                - critical_exponents: Critical scaling exponents
                - critical_regions: Regions with critical behavior
                - scaling_dimension: Effective scaling dimension
        """
        return self._critical_exponents_analyzer.analyze_critical_behavior(envelope)

    def __repr__(self) -> str:
        """String representation of power law core."""
        return f"PowerLawCore(bvp_core={self.bvp_core})"
