"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Three-soliton physical properties computation methods.

This module provides three-soliton physical properties computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class MultiSolitonPhysicalPropertiesThreeMixin:
    """Mixin providing three-soliton physical properties computation methods."""
    
    def compute_three_soliton_physical_properties(
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
        solution: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute comprehensive three-soliton physical properties.
        
        Physical Meaning:
            Computes all relevant physical properties of the three-soliton
            system including individual energies, pairwise interactions,
            three-body interactions, stability metrics, and 7D BVP specific properties.
            
        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.
            solution (Dict[str, Any]): Three-soliton solution.
            
        Returns:
            Dict[str, Any]: Complete physical properties.
        """
        try:
            # Compute individual soliton energies
            energy1 = self._compute_individual_soliton_energy(
                solution["soliton_1_profile"], solution["spatial_grid"]
            )
            energy2 = self._compute_individual_soliton_energy(
                solution["soliton_2_profile"], solution["spatial_grid"]
            )
            energy3 = self._compute_individual_soliton_energy(
                solution["soliton_3_profile"], solution["spatial_grid"]
            )
            
            # Compute pairwise interaction energies
            interaction_12 = self._compute_interaction_energy(
                amp1, width1, pos1, amp2, width2, pos2
            )
            interaction_13 = self._compute_interaction_energy(
                amp1, width1, pos1, amp3, width3, pos3
            )
            interaction_23 = self._compute_interaction_energy(
                amp2, width2, pos2, amp3, width3, pos3
            )
            
            # Compute three-body interaction energy
            three_body_energy = self._compute_three_body_interaction_energy(
                amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
            )
            
            # Compute stability metrics
            stability_metric = self._compute_three_soliton_stability(solution)
            
            # Compute phase coherence
            phase_coherence = self._compute_three_soliton_phase_coherence(solution)
            
            # Compute 7D BVP specific properties
            bvp_properties = self._compute_three_soliton_7d_bvp_properties(
                solution, amp1, width1, amp2, width2, amp3, width3
            )
            
            return {
                "individual_energies": [energy1, energy2, energy3],
                "pairwise_interactions": [
                    interaction_12,
                    interaction_13,
                    interaction_23,
                ],
                "three_body_interaction": three_body_energy,
                "total_energy": energy1
                + energy2
                + energy3
                + interaction_12
                + interaction_13
                + interaction_23
                + three_body_energy,
                "stability_metric": stability_metric,
                "phase_coherence": phase_coherence,
                "7d_bvp_properties": bvp_properties,
                "interaction_ratio": (
                    (
                        interaction_12
                        + interaction_13
                        + interaction_23
                        + three_body_energy
                    )
                    / (energy1 + energy2 + energy3)
                    if (energy1 + energy2 + energy3) > 0
                    else 0.0
                ),
            }
        
        except Exception as e:
            self.logger.error(
                f"Three-soliton physical properties computation failed: {e}"
            )
            return {}
    
    def _compute_three_soliton_stability(self, solution: Dict[str, Any]) -> float:
        """Compute three-soliton stability metric."""
        try:
            total_profile = solution["total_profile"]
            x = solution["spatial_grid"]
            
            # Compute energy distribution
            energy_density = 0.5 * (
                np.gradient(total_profile) ** 2 + self.lambda_param * total_profile**2
            )
            
            # Compute stability as energy localization
            peak_energy = np.max(energy_density)
            total_energy = np.trapz(energy_density, x)
            
            if total_energy > 0:
                return peak_energy / total_energy
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Three-soliton stability computation failed: {e}")
            return 0.0
    
    def _compute_three_soliton_phase_coherence(self, solution: Dict[str, Any]) -> float:
        """Compute three-soliton phase coherence."""
        try:
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]
            profile3 = solution["soliton_3_profile"]
            
            # Compute phase fields
            phase1 = np.arctan2(profile1, np.gradient(profile1))
            phase2 = np.arctan2(profile2, np.gradient(profile2))
            phase3 = np.arctan2(profile3, np.gradient(profile3))
            
            # Compute phase coherence as average correlation
            if len(phase1) == len(phase2) == len(phase3):
                corr_12 = np.corrcoef(phase1, phase2)[0, 1]
                corr_13 = np.corrcoef(phase1, phase3)[0, 1]
                corr_23 = np.corrcoef(phase2, phase3)[0, 1]
                
                correlations = [corr_12, corr_13, corr_23]
                valid_correlations = [c for c in correlations if not np.isnan(c)]
                
                if valid_correlations:
                    return np.mean(np.abs(valid_correlations))
                else:
                    return 0.0
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Three-soliton phase coherence computation failed: {e}")
            return 0.0
    
    def _compute_three_soliton_7d_bvp_properties(
        self,
        solution: Dict[str, Any],
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
        amp3: float,
        width3: float,
    ) -> Dict[str, Any]:
        """Compute 7D BVP specific properties for three-soliton system."""
        try:
            total_profile = solution["total_profile"]
            x = solution["spatial_grid"]
            
            # Compute fractional Laplacian contribution
            fractional_contribution = self._compute_fractional_laplacian_contribution(
                total_profile, x
            )
            
            # Compute step resonator efficiency
            step_efficiency = self._compute_three_soliton_step_efficiency(
                solution, width1, width2, width3
            )
            
            # Compute multi-body interaction efficiency
            interaction_efficiency = self._compute_three_soliton_interaction_efficiency(
                solution
            )
            
            return {
                "fractional_laplacian_contribution": fractional_contribution,
                "step_resonator_efficiency": step_efficiency,
                "multi_body_interaction_efficiency": interaction_efficiency,
                "7d_phase_space_properties": self._compute_7d_phase_space_properties(
                    total_profile, x
                ),
            }
        
        except Exception as e:
            self.logger.error(
                f"Three-soliton 7D BVP properties computation failed: {e}"
            )
            return {}
    
    def _compute_three_soliton_step_efficiency(
        self, solution: Dict[str, Any], width1: float, width2: float, width3: float
    ) -> float:
        """Compute step resonator efficiency for three-soliton system."""
        try:
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]
            profile3 = solution["soliton_3_profile"]
            x = solution["spatial_grid"]
            
            # Compute step resonator profiles
            step1 = self._step_resonator_profile(
                x, solution.get("soliton_1_position", 0.0), width1
            )
            step2 = self._step_resonator_profile(
                x, solution.get("soliton_2_position", 0.0), width2
            )
            step3 = self._step_resonator_profile(
                x, solution.get("soliton_3_position", 0.0), width3
            )
            
            # Compute efficiency as overlap for each soliton
            overlap1 = np.trapz(profile1 * step1, x)
            overlap2 = np.trapz(profile2 * step2, x)
            overlap3 = np.trapz(profile3 * step3, x)
            
            total1 = np.trapz(np.abs(profile1), x)
            total2 = np.trapz(np.abs(profile2), x)
            total3 = np.trapz(np.abs(profile3), x)
            
            efficiency1 = overlap1 / total1 if total1 > 0 else 0.0
            efficiency2 = overlap2 / total2 if total2 > 0 else 0.0
            efficiency3 = overlap3 / total3 if total3 > 0 else 0.0
            
            return (efficiency1 + efficiency2 + efficiency3) / 3.0
        
        except Exception as e:
            self.logger.error(f"Three-soliton step efficiency computation failed: {e}")
            return 0.0
    
    def _compute_three_soliton_interaction_efficiency(
        self, solution: Dict[str, Any]
    ) -> float:
        """Compute three-soliton interaction efficiency."""
        try:
            overlap_integrals = solution.get("overlap_integrals", [])
            total_field_energy = solution.get("total_field_energy", 1.0)
            
            if total_field_energy > 0 and len(overlap_integrals) >= 3:
                # Compute average interaction efficiency
                total_overlap = sum(overlap_integrals)
                return total_overlap / total_field_energy
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(
                f"Three-soliton interaction efficiency computation failed: {e}"
            )
            return 0.0

