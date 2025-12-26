"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Two-soliton physical properties computation methods.

This module provides two-soliton physical properties computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class MultiSolitonPhysicalPropertiesTwoMixin:
    """Mixin providing two-soliton physical properties computation methods."""
    
    def compute_two_soliton_physical_properties(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        solution: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute comprehensive two-soliton physical properties.
        
        Physical Meaning:
            Computes all relevant physical properties of the two-soliton
            system including individual energies, interaction energy,
            stability metrics, and 7D BVP specific properties.
            
        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            solution (Dict[str, Any]): Two-soliton solution.
            
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
            
            # Compute interaction energy
            interaction_energy = self._compute_interaction_energy(
                amp1, width1, pos1, amp2, width2, pos2
            )
            
            # Compute stability metrics
            stability_metric = self._compute_two_soliton_stability(solution)
            
            # Compute phase coherence
            phase_coherence = self._compute_two_soliton_phase_coherence(solution)
            
            # Compute 7D BVP specific properties
            bvp_properties = self._compute_two_soliton_7d_bvp_properties(
                solution, amp1, width1, amp2, width2
            )
            
            return {
                "individual_energies": [energy1, energy2],
                "interaction_energy": interaction_energy,
                "total_energy": energy1 + energy2 + interaction_energy,
                "stability_metric": stability_metric,
                "phase_coherence": phase_coherence,
                "7d_bvp_properties": bvp_properties,
                "energy_ratio": (
                    interaction_energy / (energy1 + energy2)
                    if (energy1 + energy2) > 0
                    else 0.0
                ),
            }
        
        except Exception as e:
            self.logger.error(
                f"Two-soliton physical properties computation failed: {e}"
            )
            return {}
    
    def _compute_two_soliton_stability(self, solution: Dict[str, Any]) -> float:
        """Compute two-soliton stability metric."""
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
            self.logger.error(f"Two-soliton stability computation failed: {e}")
            return 0.0
    
    def _compute_two_soliton_phase_coherence(self, solution: Dict[str, Any]) -> float:
        """Compute two-soliton phase coherence."""
        try:
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]
            
            # Compute phase fields
            phase1 = np.arctan2(profile1, np.gradient(profile1))
            phase2 = np.arctan2(profile2, np.gradient(profile2))
            
            # Compute phase coherence as correlation
            if len(phase1) == len(phase2):
                correlation = np.corrcoef(phase1, phase2)[0, 1]
                return abs(correlation) if not np.isnan(correlation) else 0.0
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(f"Two-soliton phase coherence computation failed: {e}")
            return 0.0
    
    def _compute_two_soliton_7d_bvp_properties(
        self,
        solution: Dict[str, Any],
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
    ) -> Dict[str, Any]:
        """Compute 7D BVP specific properties for two-soliton system."""
        try:
            total_profile = solution["total_profile"]
            x = solution["spatial_grid"]
            
            # Compute fractional Laplacian contribution
            fractional_contribution = self._compute_fractional_laplacian_contribution(
                total_profile, x
            )
            
            # Compute step resonator efficiency
            step_efficiency = self._compute_two_soliton_step_efficiency(
                solution, width1, width2
            )
            
            # Compute interaction efficiency
            interaction_efficiency = self._compute_interaction_efficiency(solution)
            
            return {
                "fractional_laplacian_contribution": fractional_contribution,
                "step_resonator_efficiency": step_efficiency,
                "interaction_efficiency": interaction_efficiency,
                "7d_phase_space_properties": self._compute_7d_phase_space_properties(
                    total_profile, x
                ),
            }
        
        except Exception as e:
            self.logger.error(f"Two-soliton 7D BVP properties computation failed: {e}")
            return {}
    
    def _compute_two_soliton_step_efficiency(
        self, solution: Dict[str, Any], width1: float, width2: float
    ) -> float:
        """Compute step resonator efficiency for two-soliton system."""
        try:
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]
            x = solution["spatial_grid"]
            
            # Compute step resonator profiles
            step1 = self._step_resonator_profile(
                x, solution.get("soliton_1_position", 0.0), width1
            )
            step2 = self._step_resonator_profile(
                x, solution.get("soliton_2_position", 0.0), width2
            )
            
            # Compute efficiency as overlap
            overlap1 = np.trapz(profile1 * step1, x)
            overlap2 = np.trapz(profile2 * step2, x)
            total1 = np.trapz(np.abs(profile1), x)
            total2 = np.trapz(np.abs(profile2), x)
            
            efficiency1 = overlap1 / total1 if total1 > 0 else 0.0
            efficiency2 = overlap2 / total2 if total2 > 0 else 0.0
            
            return (efficiency1 + efficiency2) / 2.0
        
        except Exception as e:
            self.logger.error(f"Two-soliton step efficiency computation failed: {e}")
            return 0.0

