"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for Level B BVP interface.

This module provides a unified interface for Level B BVP analysis,
coordinating all analysis modules through a single facade class
for fundamental field properties analysis.

Physical Meaning:
    The Level B interface facade provides a unified interface to
    all Level B analysis operations including power law analysis,
    nodes detection, topological charge computation, and zone
    separation analysis according to the 7D phase field theory.

Mathematical Foundation:
    Coordinates analysis of fundamental field properties including:
    - Power law decay A(r) ∝ r^(2β-3) in tail regions
    - Detection of spherical standing wave nodes
    - Topological charge computation using winding numbers
    - Zone separation analysis (core/transition/tail)

Example:
    >>> level_b = LevelBInterface(bvp_core)
    >>> result = level_b.process_bvp_data(envelope)
"""

import numpy as np
from typing import Dict, Any

from .bvp_level_interface_base import BVPLevelInterface
from .bvp_core import BVPCore
from .level_b_analysis import (
    PowerLawAnalyzer,
    NodesAnalyzer,
    TopologicalChargeAnalyzer,
    ZoneSeparationAnalyzer,
)


class LevelBInterface(BVPLevelInterface):
    """
    BVP integration interface for Level B (fundamental properties).

    Physical Meaning:
        Provides BVP data for Level B analysis of fundamental field
        properties including power law tails, nodes, and topological charge.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize Level B interface.

        Physical Meaning:
            Sets up the Level B interface with the BVP core and
            initializes all analysis modules for fundamental
            field properties analysis.

        Args:
            bvp_core (BVPCore): BVP core instance.
        """
        self.bvp_core = bvp_core
        self.constants = bvp_core._bvp_constants

        # Initialize analysis modules
        self.power_law_analyzer = PowerLawAnalyzer()
        self.nodes_analyzer = NodesAnalyzer()
        self.topological_charge_analyzer = TopologicalChargeAnalyzer()
        self.zone_separation_analyzer = ZoneSeparationAnalyzer()

    def process_bvp_data(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Process BVP data for Level B operations.

        Physical Meaning:
            Analyzes fundamental properties of BVP envelope including
            power law tails, absence of spherical nodes, and topological charge.

        Mathematical Foundation:
            Coordinates analysis of fundamental field properties:
            - Power law decay A(r) ∝ r^(2β-3) in tail regions
            - Detection of spherical standing wave nodes
            - Topological charge computation using winding numbers
            - Zone separation analysis (core/transition/tail)

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.
            **kwargs: Additional parameters for analysis.

        Returns:
            Dict[str, Any]: Dictionary containing all Level B analysis results.
        """
        # Analyze power law tails
        tail_data = self.power_law_analyzer.analyze_power_law_tails(envelope)

        # Check for spherical nodes
        nodes_data = self.nodes_analyzer.check_spherical_nodes(envelope)

        # Compute topological charge
        charge_data = self.topological_charge_analyzer.compute_topological_charge(
            envelope
        )

        # Analyze zone separation
        zones_data = self.zone_separation_analyzer.analyze_zone_separation(envelope)

        return {
            "envelope": envelope,
            "power_law_tails": tail_data,
            "spherical_nodes": nodes_data,
            "topological_charge": charge_data,
            "zone_separation": zones_data,
            "level": "B",
        }

    def get_detailed_analysis(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Get detailed analysis results for Level B.

        Physical Meaning:
            Provides comprehensive analysis of all Level B properties
            including detailed statistics and additional metrics.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing detailed analysis results.
        """
        # Basic analysis
        basic_results = self.process_bvp_data(envelope)

        # Additional detailed analysis
        radial_profile = self.power_law_analyzer.compute_radial_profile(envelope)
        node_distribution = self.nodes_analyzer.analyze_node_distribution(envelope)
        phase_structure = self.topological_charge_analyzer.analyze_phase_structure(
            envelope
        )
        zone_statistics = self.zone_separation_analyzer.compute_zone_statistics(
            envelope
        )

        return {
            **basic_results,
            "radial_profile": radial_profile,
            "node_distribution": node_distribution,
            "phase_structure": phase_structure,
            "zone_statistics": zone_statistics,
        }

    def validate_level_b_properties(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Validate Level B properties against theory.

        Physical Meaning:
            Validates that the BVP envelope exhibits the expected
            Level B properties according to the 7D phase field theory.

        Args:
            envelope (np.ndarray): BVP envelope field to validate.

        Returns:
            Dict[str, Any]: Dictionary containing validation results.
        """
        results = self.process_bvp_data(envelope)

        # Validate power law behavior
        tail_slope = results["power_law_tails"]["tail_slope"]
        power_law_valid = -3.0 <= tail_slope <= -1.0  # Expected range for 2β-3

        # Validate absence of spherical nodes
        has_spherical_nodes = results["spherical_nodes"]["has_spherical_nodes"]
        nodes_valid = not has_spherical_nodes  # Should be absent

        # Validate topological charge
        charge_stability = results["topological_charge"]["charge_stability"]
        charge_valid = charge_stability > 0.5  # Should be well-defined

        # Validate zone separation
        zone_indicators = results["zone_separation"]["zone_indicators"]
        N, S, C = zone_indicators["N"], zone_indicators["S"], zone_indicators["C"]
        zones_valid = (0.0 < N < 1.0) and (0.0 < S < 1.0) and (0.0 < C < 1.0)

        return {
            "power_law_valid": power_law_valid,
            "nodes_valid": nodes_valid,
            "charge_valid": charge_valid,
            "zones_valid": zones_valid,
            "overall_valid": power_law_valid
            and nodes_valid
            and charge_valid
            and zones_valid,
            "validation_details": {
                "tail_slope": tail_slope,
                "has_spherical_nodes": has_spherical_nodes,
                "charge_stability": charge_stability,
                "zone_indicators": zone_indicators,
            },
        }
