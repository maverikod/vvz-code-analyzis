"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core soliton interaction analysis functionality.

This module implements core soliton interaction analysis
including pairwise and multi-body interactions using 7D BVP theory.

Physical Meaning:
    Implements core soliton interaction analysis including
    pairwise interactions, collective properties, and
    interaction strength computation using 7D BVP theory.

Example:
    >>> analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)
    >>> analysis = analyzer.analyze_interactions(multi_solitons)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from ..base import SolitonAnalysisBase


class SolitonInteractionAnalyzer(SolitonAnalysisBase):
    """
    Core soliton interaction analyzer.

    Physical Meaning:
        Implements core soliton interaction analysis including
        pairwise interactions, collective properties, and
        interaction strength computation using 7D BVP theory.

    Mathematical Foundation:
        Computes interaction energies, stability criteria, and
        binding properties for multi-soliton systems.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton interaction analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

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
        try:
            if not multi_solitons:
                return {"total_interactions": 0, "stability_analysis": {}}

            # Extract all soliton parameters
            all_solitons = []
            for solution in multi_solitons:
                if solution.get("num_solitons", 0) > 1:
                    for i in range(1, solution["num_solitons"] + 1):
                        soliton_key = f"soliton_{i}"
                        if soliton_key in solution:
                            all_solitons.append(solution[soliton_key])

            if len(all_solitons) < 2:
                return {"total_interactions": 0, "stability_analysis": {}}

            # Compute pairwise interactions
            pairwise_interactions = []
            for i in range(len(all_solitons)):
                for j in range(i + 1, len(all_solitons)):
                    sol1 = all_solitons[i]
                    sol2 = all_solitons[j]

                    interaction = self.compute_soliton_interaction_strength(
                        sol1["amplitude"],
                        sol1["width"],
                        sol1["position"],
                        sol2["amplitude"],
                        sol2["width"],
                        sol2["position"],
                    )
                    pairwise_interactions.append(
                        {
                            "soliton_pair": (i, j),
                            "interaction_strength": interaction,
                            "distance": abs(sol2["position"] - sol1["position"]),
                        }
                    )

            # Compute collective properties
            total_interaction = sum(
                interaction["interaction_strength"]
                for interaction in pairwise_interactions
            )
            average_interaction = (
                total_interaction / len(pairwise_interactions)
                if pairwise_interactions
                else 0
            )

            # Stability analysis
            stable_pairs = sum(
                1
                for interaction in pairwise_interactions
                if interaction["interaction_strength"] > 0
            )
            stability_ratio = (
                stable_pairs / len(pairwise_interactions)
                if pairwise_interactions
                else 0
            )

            return {
                "total_interactions": len(pairwise_interactions),
                "total_interaction_strength": total_interaction,
                "average_interaction_strength": average_interaction,
                "stable_pairs": stable_pairs,
                "stability_ratio": stability_ratio,
                "pairwise_interactions": pairwise_interactions,
                "collective_stability": stability_ratio > 0.5,
            }

        except Exception as e:
            self.logger.error(f"Soliton interaction analysis failed: {e}")
            return {"total_interactions": 0, "stability_analysis": {}}

    def analyze_two_soliton_interactions(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> Dict[str, Any]:
        """
        Analyze interactions in two-soliton system.

        Physical Meaning:
            Analyzes pairwise interactions in the two-soliton system,
            including interaction strength and distance effects.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            Dict[str, Any]: Two-soliton interaction analysis.
        """
        try:
            # Compute interaction strength
            interaction_strength = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )

            # Compute distance effects
            distance = abs(pos2 - pos1)
            effective_width = (width1 + width2) / 2

            # Compute interaction range
            interaction_range = width1 + width2

            # Compute interaction efficiency
            if distance < interaction_range:
                interaction_efficiency = (
                    interaction_strength / (amp1 * amp2) if (amp1 * amp2) > 0 else 0.0
                )
            else:
                interaction_efficiency = 0.0

            return {
                "interaction_strength": interaction_strength,
                "distance": distance,
                "effective_width": effective_width,
                "interaction_range": interaction_range,
                "interaction_efficiency": interaction_efficiency,
                "is_interacting": distance < interaction_range,
            }

        except Exception as e:
            self.logger.error(f"Two-soliton interaction analysis failed: {e}")
            return {"interaction_strength": 0.0, "is_interacting": False}

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
        try:
            # Pairwise interactions
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

            # Compute interaction ratios
            total_pairwise = interaction_12 + interaction_13 + interaction_23
            pairwise_to_three_body = (
                total_pairwise / three_body_interaction
                if three_body_interaction > 0
                else float("inf")
            )

            return {
                "pairwise_interactions": {
                    "interaction_12": interaction_12,
                    "interaction_13": interaction_13,
                    "interaction_23": interaction_23,
                },
                "three_body_interaction": three_body_interaction,
                "total_interaction": total_pairwise + three_body_interaction,
                "distances": distances,
                "interaction_ratios": {
                    "pairwise_to_three_body": pairwise_to_three_body,
                    "strongest_pairwise": max(
                        interaction_12, interaction_13, interaction_23
                    ),
                    "weakest_pairwise": min(
                        interaction_12, interaction_13, interaction_23
                    ),
                },
            }

        except Exception as e:
            self.logger.error(f"Three-soliton interaction analysis failed: {e}")
            return {"total_interaction": 0.0, "is_stable": False}

    def _step_resonator_interaction(
        self, distance: float, interaction_range: float
    ) -> float:
        """
        Step resonator interaction function using 7D BVP theory.

        Physical Meaning:
            Implements step resonator interaction instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at interaction range.

        Mathematical Foundation:
            Step function interaction:
            f(d) = 1 if d < R, 0 if d ≥ R
            where R is the interaction range.

        Args:
            distance (float): Distance between solitons.
            interaction_range (float): Interaction range.

        Returns:
            float: Step resonator interaction factor.
        """
        try:
            # Step resonator: sharp cutoff at interaction range
            if distance < interaction_range:
                return 1.0
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Step resonator interaction computation failed: {e}")
            return 0.0
