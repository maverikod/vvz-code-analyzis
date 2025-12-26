"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main power law core analysis for BVP framework.

This module implements the main power law analysis functionality
for the BVP framework.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from ..bvp_core.bvp_core_facade import BVPCoreFacade as BVPCore
from .power_law_tail_analysis import PowerLawTailAnalysis
from .power_law_region_analysis import PowerLawRegionAnalysis
from .power_law_fitting import PowerLawFitting


class PowerLawCoreMain:
    """
    Main power law analyzer for BVP framework.

    Physical Meaning:
        Analyzes the power law decay of BVP envelope amplitude in the
        tail region, which characterizes the field's long-range behavior
        in homogeneous medium according to the 7D phase field theory.

    Mathematical Foundation:
        Computes power law decay A(r) ∝ r^(2β-3) in the tail region,
        where β is the fractional order and r is the radial distance
        from the field center.
    """

    def __init__(self, bvp_core: BVPCore = None):
        """
        Initialize unified power law analyzer.

        Physical Meaning:
            Sets up the analyzer with the BVP core for accessing
            field data and computational resources.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Analysis parameters
        self.tail_threshold = 0.1  # Threshold for tail region
        self.min_tail_points = 10  # Minimum points for tail analysis
        self.power_law_tolerance = 1e-3  # Tolerance for power law fitting

        # Initialize specialized modules
        self.tail_analysis = PowerLawTailAnalysis(bvp_core)
        self.region_analysis = PowerLawRegionAnalysis(bvp_core)
        self.fitting = PowerLawFitting(bvp_core)

    def analyze_power_laws(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze power law behavior of BVP envelope field.

        Physical Meaning:
            Analyzes the power law decay characteristics of the BVP envelope
            field, which describes the long-range behavior of the field
            in the 7D phase field theory.

        Mathematical Foundation:
            Computes power law decay A(r) ∝ r^(2β-3) where:
            - A(r) is the envelope amplitude at distance r
            - β is the fractional order parameter
            - The decay rate characterizes field behavior

        Args:
            envelope (np.ndarray): BVP envelope field data.

        Returns:
            Dict[str, Any]: Power law analysis results including:
                - power_law_exponents: List of fitted power law exponents
                - decay_rates: List of calculated decay rates
                - fitting_qualities: List of fitting quality metrics
                - tail_regions: List of identified tail regions
                - overall_characteristics: Overall field characteristics

        Raises:
            ValueError: If envelope data is invalid or empty.
            RuntimeError: If power law analysis fails.
        """
        if envelope is None or envelope.size == 0:
            raise ValueError("Envelope data cannot be None or empty")

        self.logger.info("Starting power law analysis of BVP envelope field")

        # Analyze tail regions
        tail_analyses = self.tail_analysis.analyze_power_law_tails(envelope)

        # Analyze regions
        region_analyses = self.region_analysis.analyze_regions(envelope)

        # Combine results
        power_law_results = tail_analyses + region_analyses

        # Calculate overall characteristics
        overall_characteristics = self._calculate_overall_characteristics(
            power_law_results
        )

        # Extract key metrics
        power_law_exponents = [
            result.get("power_law_exponent", 0.0) for result in power_law_results
        ]
        decay_rates = [result.get("decay_rate", 0.0) for result in power_law_results]
        fitting_qualities = [
            result.get("fitting_quality", 0.0) for result in power_law_results
        ]
        tail_regions = [result.get("region", {}) for result in power_law_results]

        results = {
            "power_law_exponents": power_law_exponents,
            "decay_rates": decay_rates,
            "fitting_qualities": fitting_qualities,
            "tail_regions": tail_regions,
            "overall_characteristics": overall_characteristics,
            "number_of_regions": len(power_law_results),
            "analysis_successful": len(power_law_results) > 0,
        }

        self.logger.info(
            f"Power law analysis completed: {len(power_law_results)} regions analyzed"
        )
        return results

    def _calculate_overall_characteristics(
        self, power_law_results: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate overall characteristics from power law results.

        Physical Meaning:
            Computes overall characteristics of the power law behavior
            across all analyzed regions.

        Args:
            power_law_results (List[Dict[str, Any]]): List of power law analysis results.

        Returns:
            Dict[str, float]: Overall characteristics including mean values and statistics.
        """
        if not power_law_results:
            return {
                "mean_power_law_exponent": 0.0,
                "mean_decay_rate": 0.0,
                "mean_fitting_quality": 0.0,
                "std_power_law_exponent": 0.0,
                "std_decay_rate": 0.0,
                "std_fitting_quality": 0.0,
            }

        # Extract metrics
        exponents = [
            result.get("power_law_exponent", 0.0) for result in power_law_results
        ]
        decay_rates = [result.get("decay_rate", 0.0) for result in power_law_results]
        qualities = [result.get("fitting_quality", 0.0) for result in power_law_results]

        # Calculate statistics
        return {
            "mean_power_law_exponent": float(np.mean(exponents)),
            "mean_decay_rate": float(np.mean(decay_rates)),
            "mean_fitting_quality": float(np.mean(qualities)),
            "std_power_law_exponent": float(np.std(exponents)),
            "std_decay_rate": float(np.std(decay_rates)),
            "std_fitting_quality": float(np.std(qualities)),
        }
