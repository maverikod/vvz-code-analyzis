"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pinned beating analysis module.

This module implements pinned beating analysis functionality
for Level C test C4 in 7D phase field theory.

Physical Meaning:
    Analyzes mode beating with pinning effects, including
    drift suppression and beating pattern modification.

Example:
    >>> analyzer = PinnedBeatingAnalyzer(bvp_core)
    >>> results = analyzer.analyze_pinned_beating(domain, dual_mode, time_params, pinning_params)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import DualModeSource
from .pinned_analysis_field_creation import PinnedFieldCreator
from .pinned_analysis_evolution import PinnedFieldEvolution
from .pinned_analysis_patterns import PinnedPatternAnalyzer
from .pinned_analysis_suppression import PinnedSuppressionAnalyzer


class PinnedBeatingAnalyzer:
    """
    Pinned beating analysis for Level C test C4.

    Physical Meaning:
        Analyzes mode beating with pinning effects, including
        drift suppression and beating pattern modification.

    Mathematical Foundation:
        Implements pinned beating analysis:
        - Dual-mode field with pinning effects
        - Drift suppression analysis with pinning
        - Beating pattern modification due to pinning
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize pinned beating analyzer.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize analysis components
        self._field_creator = PinnedFieldCreator()
        self._field_evolution = PinnedFieldEvolution()
        self._pattern_analyzer = PinnedPatternAnalyzer()
        self._suppression_analyzer = PinnedSuppressionAnalyzer()

    def analyze_pinned_beating(
        self,
        domain: Dict[str, Any],
        dual_mode: DualModeSource,
        time_params: Dict[str, Any],
        pinning_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze pinned beating with pinning effects.

        Physical Meaning:
            Analyzes mode beating with pinning effects,
            including drift suppression and beating pattern modification.

        Mathematical Foundation:
            Analyzes the system response to dual-mode excitation with pinning:
            - Dual-mode field with pinning: s(x,t) = s₁(x) e^(-iω₁t) + s₂(x) e^(-iω₂t) + p(x)
            - Drift suppression analysis with pinning effects
            - Beating pattern modification due to pinning

        Args:
            domain (Dict[str, Any]): Domain parameters.
            dual_mode (DualModeSource): Dual-mode source specification.
            time_params (Dict[str, Any]): Time evolution parameters.
            pinning_params (Dict[str, Any]): Pinning parameters.

        Returns:
            Dict[str, Any]: Pinned beating analysis results.
        """
        self.logger.info("Starting pinned beating analysis")

        # Create pinned dual-mode field
        field_pinned = self._field_creator.create_pinned_dual_mode_field(
            domain, dual_mode, pinning_params
        )

        # Perform time evolution with pinning
        time_evolution = self._field_evolution.evolve_pinned_dual_mode_field(
            field_pinned, dual_mode, time_params, pinning_params
        )

        # Analyze pinned beating patterns
        beating_pattern = self._pattern_analyzer.analyze_pinned_beating_patterns(
            time_evolution, dual_mode, pinning_params
        )

        # Analyze drift suppression
        drift_suppression = self._suppression_analyzer.analyze_drift_suppression(
            time_evolution, pinning_params
        )

        self.logger.info("Pinned beating analysis completed")

        return {
            "field_evolution": time_evolution,
            "beating_pattern": beating_pattern,
            "drift_suppression": drift_suppression,
            "analysis_complete": True,
            "pinning_effects_detected": True,
        }
