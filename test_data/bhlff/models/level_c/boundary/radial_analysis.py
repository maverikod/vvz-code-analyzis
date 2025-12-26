"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radial analysis module for boundary effects.

This module implements radial analysis functionality
for Level C test C1 in 7D phase field theory.

Physical Meaning:
    Analyzes radial profiles for boundary effects,
    including field distribution and concentration patterns.

Example:
    >>> analyzer = RadialAnalyzer(bvp_core)
    >>> results = analyzer.analyze_radial_profile(domain, boundary, field)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, RadialProfile
from .radial_analysis_core import RadialAnalysisCore
from .radial_analysis_concentration import RadialConcentrationAnalyzer


class RadialAnalyzer:
    """
    Radial analysis for boundary effects.

    Physical Meaning:
        Analyzes radial profiles for boundary effects,
        including field distribution and concentration patterns.

    Mathematical Foundation:
        Implements radial analysis:
        - Radial profile: A(r) = (1/4π) ∫_S(r) |a(x)|² dS
        - Local maxima detection in radial profiles
        - Field concentration analysis
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize radial analyzer.

        Physical Meaning:
            Sets up the radial analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize analysis components
        self._core_analyzer = RadialAnalysisCore(bvp_core)
        self._concentration_analyzer = RadialConcentrationAnalyzer(bvp_core)

    def analyze_radial_profile(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> RadialProfile:
        """
        Analyze radial profile.

        Physical Meaning:
            Analyzes radial profile for boundary effects
            including field distribution and concentration patterns.

        Mathematical Foundation:
            Radial profile: A(r) = (1/4π) ∫_S(r) |a(x)|² dS

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            RadialProfile: Radial profile analysis results.
        """
        return self._core_analyzer.analyze_radial_profile(domain, boundary, field)

    def analyze_field_concentration(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze field concentration.

        Physical Meaning:
            Analyzes field concentration patterns for boundary effects
            including near-boundary and far-boundary concentration.

        Mathematical Foundation:
            Analyzes concentration patterns through:
            - Near-boundary concentration analysis
            - Far-boundary concentration analysis
            - Overall concentration pattern analysis

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Field concentration analysis results.
        """
        return self._concentration_analyzer.analyze_field_concentration(
            domain, boundary, field
        )
