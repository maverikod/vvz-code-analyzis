"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton interaction analysis and stability facade.

This module provides the main interface for soliton interaction analysis
functionality, combining core interaction operations with
stability analysis and binding properties.

Physical Meaning:
    Provides comprehensive soliton interaction analysis including
    stability, binding energy, and collective properties using
    7D BVP theory principles.

Example:
    >>> analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)
    >>> analysis = analyzer.analyze_interactions(multi_solitons)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .base import SolitonAnalysisBase
from .interaction_analysis import (
    SolitonInteractionAnalyzer as CoreInteractionAnalyzer,
    SolitonStabilityAnalyzer,
    SolitonModeAnalyzer,
    SolitonBindingAnalyzer,
)


class SolitonInteractionAnalyzer(SolitonAnalysisBase):
    """
    Soliton interaction analyzer and stability assessor facade.

    Physical Meaning:
        Provides comprehensive soliton interaction analysis including
        stability, binding energy, and collective properties using
        7D BVP theory principles.

    Mathematical Foundation:
        Combines core interaction operations with stability analysis
        and binding properties for complete soliton interaction analysis.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton interaction analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.core = CoreInteractionAnalyzer(system, nonlinear_params)
        self.stability = SolitonStabilityAnalyzer(system, nonlinear_params)
        self.mode = SolitonModeAnalyzer(system, nonlinear_params)
        self.binding = SolitonBindingAnalyzer(system, nonlinear_params)

    def analyze_interactions(
        self, multi_solitons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze interactions between multiple solitons.

        Physical Meaning:
            Analyzes the collective interaction properties of multiple
            solitons, including stability, binding, and coherence.

        Args:
            multi_solitons (List[Dict[str, Any]]): List of multi-soliton solutions.

        Returns:
            Dict[str, Any]: Comprehensive interaction analysis.
        """
        return self.core.analyze_interactions(multi_solitons)

    def analyze_two_soliton_stability(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> Dict[str, Any]:
        """
        Analyze stability of two-soliton configuration.

        Physical Meaning:
            Determines the stability properties of the two-soliton system,
            including binding energy and stability criteria.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            Dict[str, Any]: Stability analysis results.
        """
        return self.stability.analyze_two_soliton_stability(
            amp1, width1, pos1, amp2, width2, pos2
        )

    def analyze_three_soliton_interactions(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> Dict[str, Any]:
        """
        Analyze interactions in three-soliton system.

        Physical Meaning:
            Analyzes all pairwise and three-body interactions in the
            three-soliton system, including stability and binding properties.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            Dict[str, Any]: Complete interaction analysis.
        """
        return self.core.analyze_three_soliton_interactions(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def analyze_three_soliton_stability(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> Dict[str, Any]:
        """
        Analyze stability of three-soliton configuration.

        Physical Meaning:
            Determines the stability properties of the three-soliton system,
            including binding energy, stability criteria, and mode analysis.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            Dict[str, Any]: Comprehensive stability analysis.
        """
        return self.stability.analyze_three_soliton_stability(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def _compute_full_mode_analysis(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> Dict[str, Any]:
        """
        Compute full mode analysis for three-soliton system using 7D BVP theory.

        Physical Meaning:
            Performs complete mode analysis of the three-soliton system,
            including collective modes, stability eigenvalues, and
            interaction-induced mode splitting.

        Mathematical Foundation:
            Computes the full eigenvalue spectrum of the three-soliton
            system using 7D fractional Laplacian equations and
            soliton-soliton interaction potentials.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            Dict[str, Any]: Complete mode analysis results.
        """
        return self.mode.compute_full_mode_analysis(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )
