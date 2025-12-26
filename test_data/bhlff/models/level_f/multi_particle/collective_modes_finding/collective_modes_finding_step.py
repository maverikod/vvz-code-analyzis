"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step function methods for collective modes finding.

This module provides step function methods as a mixin class.
"""


class CollectiveModesFindingStepMixin:
    """Mixin providing step function methods."""
    
    def _step_interaction_potential(self, distance: float) -> float:
        """
        Step function interaction potential.
        
        Physical Meaning:
            Implements step resonator model for particle interactions instead of
            exponential decay. This follows 7D BVP theory principles where
            interactions occur through semi-transparent boundaries.
            
        Mathematical Foundation:
            V(r) = V₀ * Θ(r_cutoff - r) where Θ is the Heaviside step function
            and r_cutoff is the interaction cutoff distance.
            
        Args:
            distance: Distance between particles
            
        Returns:
            Step function interaction potential
        """
        # Step resonator parameters
        interaction_cutoff = self.system_params.interaction_range
        interaction_strength = self.system_params.get("interaction_strength", 1.0)
        
        # Step function interaction: 1.0 below cutoff, 0.0 above
        return interaction_strength if distance < interaction_cutoff else 0.0
    
    def _step_resonator_phase_coherence(self, distance: float) -> float:
        """
        Step resonator phase coherence according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function phase coherence instead of exponential decay
            according to 7D BVP theory principles where phase coherence is determined
            by step functions rather than smooth transitions.
            
        Mathematical Foundation:
            Phase coherence = Θ(distance_cutoff - distance) where Θ is the Heaviside step function
            and distance_cutoff is the cutoff distance for phase coherence.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Step function phase coherence according to 7D BVP theory.
        """
        # Step function phase coherence according to 7D BVP theory
        cutoff_distance = 2.0
        coherence_strength = 1.0
        
        # Apply step function boundary condition
        if distance < cutoff_distance:
            return coherence_strength
        else:
            return 0.0

