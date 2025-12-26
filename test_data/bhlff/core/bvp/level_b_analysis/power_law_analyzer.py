"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law tail analyzer for Level B BVP interface.

This module provides a wrapper around the unified power law analyzer
for backward compatibility with existing Level B BVP interface.

Physical Meaning:
    Analyzes the power law decay of BVP envelope amplitude in the tail
    region, which characterizes the field's long-range behavior in
    homogeneous medium according to the 7D phase field theory.

Mathematical Foundation:
    Computes power law decay A(r) ∝ r^(2β-3) in the tail region,
    where β is the fractional order and r is the radial distance
    from the field center.

Example:
    >>> analyzer = PowerLawAnalyzer()
    >>> tail_data = analyzer.analyze_power_law_tails(envelope)
"""

import numpy as np
from typing import Dict, Any
from ..unified_power_law_analyzer import UnifiedPowerLawAnalyzer


class PowerLawAnalyzer:
    """
    Power law tail analyzer for Level B BVP interface.

    Physical Meaning:
        Analyzes the power law decay of BVP envelope amplitude in the
        tail region, which characterizes the field's long-range behavior
        in homogeneous medium according to the 7D phase field theory.

    Mathematical Foundation:
        Computes power law decay A(r) ∝ r^(2β-3) in the tail region,
        where β is the fractional order and r is the radial distance
        from the field center.
    """

    def __init__(self):
        """Initialize power law analyzer."""
        self._unified_analyzer = UnifiedPowerLawAnalyzer()

    def analyze_power_law_tails(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze power law tails in homogeneous medium.

        Physical Meaning:
            Computes the power law decay of BVP envelope amplitude
            in the tail region, which characterizes the field's
            long-range behavior in homogeneous medium.

        Mathematical Foundation:
            Fits power law A(r) ∝ r^α in the tail region using
            linear regression on log-log scale: log(A) = α log(r) + C

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - tail_slope: Power law exponent α
                - r_squared: R-squared value of the fit
                - power_law_range: Range of radial distances used
        """
        return self._unified_analyzer.analyze_power_law_tails(envelope)

    def compute_radial_profile(
        self, envelope: np.ndarray, n_bins: int = 50
    ) -> Dict[str, Any]:
        """
        Compute radial profile of envelope amplitude.

        Physical Meaning:
            Computes the radial average of envelope amplitude for
            analysis of field structure and power law behavior.

        Args:
            envelope (np.ndarray): BVP envelope field.
            n_bins (int): Number of radial bins.

        Returns:
            Dict[str, Any]: Dictionary containing radial profile data.
        """
        return self._unified_analyzer.compute_radial_profile(envelope, n_bins)
