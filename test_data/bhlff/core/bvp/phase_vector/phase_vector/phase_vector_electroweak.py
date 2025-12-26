"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Electroweak currents methods for phase vector.

This module provides methods for computing electroweak currents as a mixin class.
"""

import numpy as np
from typing import Dict


class PhaseVectorElectroweakMixin:
    """Mixin providing electroweak currents methods."""
    
    def compute_electroweak_currents(
        self, envelope: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents as functionals of the envelope.
        
        Physical Meaning:
            Computes electromagnetic and weak currents that are
            generated as functionals of the BVP envelope through
            the U(1)³ phase structure.
            
        Mathematical Foundation:
            J_EM = g_EM * |A|² * ∇Θ_EM
            J_weak = g_weak * |A|⁴ * ∇Θ_weak
            where Θ_EM and Θ_weak are combinations of Θ_a components.
            
        Args:
            envelope (np.ndarray): BVP envelope |A|.
            
        Returns:
            Dict[str, np.ndarray]: Electroweak currents including:
                - em_current: Electromagnetic current
                - weak_current: Weak interaction current
                - mixed_current: Mixed electroweak current
        """
        # Check memory usage before computation
        self._check_memory_usage("electroweak_currents_start")
        
        try:
            phase_components = self._phase_components.get_components()
            result = self._electroweak_coupling.compute_electroweak_currents(
                envelope, phase_components, self.domain
            )
            
            # Check memory usage after computation
            self._check_memory_usage("electroweak_currents_end")
            
            return result
        except Exception as e:
            self.logger.error(f"Error in electroweak currents computation: {e}")
            # Force memory cleanup on error
            self.force_memory_cleanup()
            raise

