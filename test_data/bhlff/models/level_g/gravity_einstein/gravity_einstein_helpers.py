"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for phase envelope balance solver.

This module provides helper methods as a mixin class.
"""

import numpy as np


class PhaseEnvelopeBalanceSolverHelpersMixin:
    """Mixin providing helper methods."""
    
    def _step_resonator_transmission(self, k_magnitude: np.ndarray) -> np.ndarray:
        """
        Step resonator transmission coefficient.
        
        Physical Meaning:
            Implements step resonator model for energy exchange instead of
            exponential decay. This follows 7D BVP theory principles where
            energy exchange occurs through semi-transparent boundaries.
        """
        # Step resonator parameters
        cutoff_frequency = self.params.get("resonator_cutoff_frequency", 10.0)
        transmission_coeff = self.params.get("transmission_coefficient", 0.9)

        # Step function transmission: 1.0 below cutoff, 0.0 above
        return transmission_coeff * np.where(k_magnitude < cutoff_frequency, 1.0, 0.0)

