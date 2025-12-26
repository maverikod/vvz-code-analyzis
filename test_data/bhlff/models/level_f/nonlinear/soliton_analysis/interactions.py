"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton interaction analysis facade.

This module provides the main interface for soliton interaction analysis
functionality, combining interaction analysis with mode analysis
for comprehensive multi-soliton system characterization.

Physical Meaning:
    Provides comprehensive soliton interaction analysis including
    stability, binding energy, collective properties, and mode
    analysis for multi-soliton systems using 7D phase field theory.

Example:
    >>> analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)
    >>> analysis = analyzer.analyze_interactions(multi_solitons)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .base import SolitonAnalysisBase
from .interaction_analyzer import SolitonInteractionAnalyzer
from .mode_analysis import SolitonModeAnalyzer


class SolitonInteractionAnalyzer(SolitonAnalysisBase):
    """
    Soliton interaction analyzer facade.

    Physical Meaning:
        Provides comprehensive soliton interaction analysis including
        stability, binding energy, collective properties, and mode
        analysis for multi-soliton systems using 7D phase field theory.

    Mathematical Foundation:
        Combines interaction analysis with mode analysis for complete
        characterization of multi-soliton systems.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton interaction analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.interaction_analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)
        self.mode_analyzer = SolitonModeAnalyzer(system, nonlinear_params)

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
        return self.interaction_analyzer.analyze_interactions(multi_solitons)

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
        return self.interaction_analyzer.analyze_two_soliton_stability(
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
        return self.interaction_analyzer.analyze_three_soliton_interactions(
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
        return self.interaction_analyzer.analyze_three_soliton_stability(
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
        return self.interaction_analyzer._compute_full_mode_analysis(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def _compute_interaction_matrix(
        self,
        x: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> np.ndarray:
        """Delegate to mode analyzer."""
        return self.mode_analyzer._compute_interaction_matrix(
            x, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def _compute_kinetic_matrix(self, x: np.ndarray) -> np.ndarray:
        """Delegate to mode analyzer."""
        return self.mode_analyzer._compute_kinetic_matrix(x)

    def _compute_mode_participation_ratios(
        self,
        eigenvectors: np.ndarray,
        profile1: np.ndarray,
        profile2: np.ndarray,
        profile3: np.ndarray,
    ) -> Dict[str, Any]:
        """Delegate to mode analyzer."""
        return self.mode_analyzer._compute_mode_participation_ratios(
            eigenvectors, profile1, profile2, profile3
        )

    def _compute_mode_splitting(
        self,
        eigenvalues: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> float:
        """Delegate to mode analyzer."""
        return self.mode_analyzer._compute_mode_splitting(
            eigenvalues, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )
