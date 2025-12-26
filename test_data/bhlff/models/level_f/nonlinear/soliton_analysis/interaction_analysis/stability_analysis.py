"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton stability analysis functionality.

This module implements soliton stability analysis including
binding energy, stability criteria, and mode analysis using 7D BVP theory.

Physical Meaning:
    Implements soliton stability analysis including binding energy,
    stability criteria, and mode analysis for multi-soliton systems.

Example:
    >>> analyzer = SolitonStabilityAnalyzer(system, nonlinear_params)
    >>> stability = analyzer.analyze_two_soliton_stability(amp1, width1, pos1, amp2, width2, pos2)
"""

import numpy as np
from typing import Dict, Any
import logging

from ..base import SolitonAnalysisBase


class SolitonStabilityAnalyzer(SolitonAnalysisBase):
    """
    Soliton stability analyzer.

    Physical Meaning:
        Implements soliton stability analysis including binding energy,
        stability criteria, and mode analysis for multi-soliton systems.

    Mathematical Foundation:
        Computes stability criteria, binding energies, and
        mode analysis for soliton systems.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton stability analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

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
        try:
            # Compute binding energy
            individual_energy1 = amp1**2 / (2 * width1**2)
            individual_energy2 = amp2**2 / (2 * width2**2)
            interaction_energy = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )

            binding_energy = (
                individual_energy1 + individual_energy2 - interaction_energy
            )

            # Stability criteria
            distance = abs(pos2 - pos1)
            critical_distance = (width1 + width2) / 2

            is_stable = binding_energy > 0 and distance > critical_distance
            is_bound = binding_energy > 0

            return {
                "binding_energy": binding_energy,
                "individual_energies": [individual_energy1, individual_energy2],
                "interaction_energy": interaction_energy,
                "is_stable": is_stable,
                "is_bound": is_bound,
                "critical_distance": critical_distance,
                "actual_distance": distance,
                "stability_ratio": binding_energy
                / (individual_energy1 + individual_energy2),
            }

        except Exception as e:
            self.logger.error(f"Two-soliton stability analysis failed: {e}")
            return {"is_stable": False, "binding_energy": 0.0}

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
        try:
            # Compute all interaction energies
            interaction_12 = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )
            interaction_13 = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp3, width3, pos3
            )
            interaction_23 = self.compute_soliton_interaction_strength(
                amp2, width2, pos2, amp3, width3, pos3
            )

            # Three-body interaction
            distances = [abs(pos2 - pos1), abs(pos3 - pos1), abs(pos3 - pos2)]
            total_distance = sum(distances)
            effective_width = (width1 + width2 + width3) / 3

            three_body_interaction = (
                self.three_body_strength
                * amp1
                * amp2
                * amp3
                * self._step_resonator_interaction(total_distance, effective_width)
            )

            # Individual energies
            individual_energies = [
                amp1**2 / (2 * width1**2),
                amp2**2 / (2 * width2**2),
                amp3**2 / (2 * width3**2),
            ]

            # Total interaction energy
            total_interaction = (
                interaction_12
                + interaction_13
                + interaction_23
                + three_body_interaction
            )
            binding_energy = sum(individual_energies) - total_interaction

            # Stability criteria
            critical_distances = [
                (width1 + width2) / 2,
                (width1 + width3) / 2,
                (width2 + width3) / 2,
            ]

            # Check if all pairs are stable
            pairwise_stable = all(
                d > cd for d, cd in zip(distances, critical_distances)
            )

            # Overall stability
            is_stable = binding_energy > 0 and pairwise_stable

            # Stability margin
            stability_margin = (
                min(d / cd for d, cd in zip(distances, critical_distances))
                if all(cd > 0 for cd in critical_distances)
                else 0
            )

            return {
                "is_stable": is_stable,
                "pairwise_stable": pairwise_stable,
                "binding_energy": binding_energy,
                "individual_energies": individual_energies,
                "total_interaction": total_interaction,
                "critical_distances": critical_distances,
                "actual_distances": distances,
                "stability_margin": stability_margin,
                "interaction_breakdown": {
                    "pairwise_12": interaction_12,
                    "pairwise_13": interaction_13,
                    "pairwise_23": interaction_23,
                    "three_body": three_body_interaction,
                },
            }

        except Exception as e:
            self.logger.error(f"Three-soliton stability analysis failed: {e}")
            return {"is_stable": False, "binding_energy": 0.0}

    def _step_resonator_interaction(
        self, distance: float, interaction_range: float
    ) -> float:
        """Step resonator interaction function using 7D BVP theory."""
        try:
            if distance < interaction_range:
                return 1.0
            else:
                return 0.0
        except Exception as e:
            self.logger.error(f"Step resonator interaction computation failed: {e}")
            return 0.0
