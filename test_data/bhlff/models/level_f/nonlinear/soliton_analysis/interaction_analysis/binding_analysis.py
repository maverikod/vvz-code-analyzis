"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton binding analysis functionality.

This module implements soliton binding analysis including
binding energy, binding strength, and collective binding
properties using 7D BVP theory.

Physical Meaning:
    Implements soliton binding analysis including binding energy,
    binding strength, and collective binding properties for
    multi-soliton systems.

Example:
    >>> analyzer = SolitonBindingAnalyzer(system, nonlinear_params)
    >>> binding = analyzer.analyze_binding_energy(amp1, width1, pos1, amp2, width2, pos2)
"""

import numpy as np
from typing import Dict, Any
import logging

from ..base import SolitonAnalysisBase


class SolitonBindingAnalyzer(SolitonAnalysisBase):
    """
    Soliton binding analyzer.

    Physical Meaning:
        Implements soliton binding analysis including binding energy,
        binding strength, and collective binding properties for
        multi-soliton systems.

    Mathematical Foundation:
        Computes binding energies, binding strengths, and
        collective binding properties for soliton systems.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton binding analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def analyze_binding_energy(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> Dict[str, Any]:
        """
        Analyze binding energy of two-soliton system.

        Physical Meaning:
            Computes the binding energy of the two-soliton system,
            including individual energies and interaction energy.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            Dict[str, Any]: Binding energy analysis.
        """
        try:
            # Compute individual soliton energies
            energy1 = amp1**2 / (2 * width1**2)
            energy2 = amp2**2 / (2 * width2**2)

            # Compute interaction energy
            interaction_energy = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )

            # Compute binding energy
            binding_energy = energy1 + energy2 - interaction_energy

            # Compute binding strength
            binding_strength = (
                binding_energy / (energy1 + energy2) if (energy1 + energy2) > 0 else 0.0
            )

            # Compute binding efficiency
            distance = abs(pos2 - pos1)
            effective_width = (width1 + width2) / 2
            binding_efficiency = (
                binding_energy / (effective_width * distance)
                if (effective_width * distance) > 0
                else 0.0
            )

            return {
                "binding_energy": binding_energy,
                "individual_energies": [energy1, energy2],
                "interaction_energy": interaction_energy,
                "binding_strength": binding_strength,
                "binding_efficiency": binding_efficiency,
                "is_bound": binding_energy > 0,
                "binding_ratio": (
                    binding_energy / (energy1 + energy2)
                    if (energy1 + energy2) > 0
                    else 0.0
                ),
            }

        except Exception as e:
            self.logger.error(f"Binding energy analysis failed: {e}")
            return {"binding_energy": 0.0, "is_bound": False}

    def analyze_three_soliton_binding(
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
        Analyze binding energy of three-soliton system.

        Physical Meaning:
            Computes the binding energy of the three-soliton system,
            including individual energies, pairwise interactions,
            and three-body interactions.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            Dict[str, Any]: Three-soliton binding analysis.
        """
        try:
            # Compute individual soliton energies
            energy1 = amp1**2 / (2 * width1**2)
            energy2 = amp2**2 / (2 * width2**2)
            energy3 = amp3**2 / (2 * width3**2)

            # Compute pairwise interaction energies
            interaction_12 = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )
            interaction_13 = self.compute_soliton_interaction_strength(
                amp1, width1, pos1, amp3, width3, pos3
            )
            interaction_23 = self.compute_soliton_interaction_strength(
                amp2, width2, pos2, amp3, width3, pos3
            )

            # Compute three-body interaction energy
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

            # Compute total binding energy
            total_interaction = (
                interaction_12
                + interaction_13
                + interaction_23
                + three_body_interaction
            )
            binding_energy = energy1 + energy2 + energy3 - total_interaction

            # Compute binding strength
            total_individual = energy1 + energy2 + energy3
            binding_strength = (
                binding_energy / total_individual if total_individual > 0 else 0.0
            )

            # Compute binding efficiency
            average_distance = np.mean(distances)
            binding_efficiency = (
                binding_energy / (average_distance * effective_width)
                if (average_distance * effective_width) > 0
                else 0.0
            )

            return {
                "binding_energy": binding_energy,
                "individual_energies": [energy1, energy2, energy3],
                "pairwise_interactions": [
                    interaction_12,
                    interaction_13,
                    interaction_23,
                ],
                "three_body_interaction": three_body_interaction,
                "total_interaction": total_interaction,
                "binding_strength": binding_strength,
                "binding_efficiency": binding_efficiency,
                "is_bound": binding_energy > 0,
                "binding_ratio": (
                    binding_energy / total_individual if total_individual > 0 else 0.0
                ),
                "interaction_breakdown": {
                    "pairwise_12": interaction_12,
                    "pairwise_13": interaction_13,
                    "pairwise_23": interaction_23,
                    "three_body": three_body_interaction,
                },
            }

        except Exception as e:
            self.logger.error(f"Three-soliton binding analysis failed: {e}")
            return {"binding_energy": 0.0, "is_bound": False}

    def analyze_collective_binding(self, multi_solitons: list) -> Dict[str, Any]:
        """
        Analyze collective binding properties of multiple solitons.

        Physical Meaning:
            Computes collective binding properties of multiple solitons,
            including total binding energy, binding distribution,
            and collective stability.

        Args:
            multi_solitons (list): List of multi-soliton solutions.

        Returns:
            Dict[str, Any]: Collective binding analysis.
        """
        try:
            if not multi_solitons:
                return {"total_binding_energy": 0.0, "collective_stability": False}

            # Extract all soliton parameters
            all_solitons = []
            for solution in multi_solitons:
                if solution.get("num_solitons", 0) > 1:
                    for i in range(1, solution["num_solitons"] + 1):
                        soliton_key = f"soliton_{i}"
                        if soliton_key in solution:
                            all_solitons.append(solution[soliton_key])

            if len(all_solitons) < 2:
                return {"total_binding_energy": 0.0, "collective_stability": False}

            # Compute individual energies
            individual_energies = []
            for soliton in all_solitons:
                energy = soliton["amplitude"] ** 2 / (2 * soliton["width"] ** 2)
                individual_energies.append(energy)

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
                    pairwise_interactions.append(interaction)

            # Compute total binding energy
            total_individual_energy = sum(individual_energies)
            total_interaction_energy = sum(pairwise_interactions)
            total_binding_energy = total_individual_energy - total_interaction_energy

            # Compute collective binding strength
            collective_binding_strength = (
                total_binding_energy / total_individual_energy
                if total_individual_energy > 0
                else 0.0
            )

            # Compute collective stability
            stable_interactions = sum(
                1 for interaction in pairwise_interactions if interaction > 0
            )
            collective_stability = (
                stable_interactions / len(pairwise_interactions)
                if pairwise_interactions
                else 0.0
            )

            return {
                "total_binding_energy": total_binding_energy,
                "individual_energies": individual_energies,
                "pairwise_interactions": pairwise_interactions,
                "collective_binding_strength": collective_binding_strength,
                "collective_stability": collective_stability,
                "stable_interactions": stable_interactions,
                "total_interactions": len(pairwise_interactions),
            }

        except Exception as e:
            self.logger.error(f"Collective binding analysis failed: {e}")
            return {"total_binding_energy": 0.0, "collective_stability": False}

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
