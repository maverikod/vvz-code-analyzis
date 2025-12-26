"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase components methods for phase vector.

This module provides methods for working with phase components as a mixin class.
"""

import numpy as np
from typing import List


class PhaseVectorComponentsMixin:
    """Mixin providing phase components methods."""
    
    def get_phase_components(self) -> List[np.ndarray]:
        """
        Get the three U(1) phase components Θ_a (a=1..3).
        
        Physical Meaning:
            Returns the three independent U(1) phase components
            that form the U(1)³ structure.
            
        Returns:
            List[np.ndarray]: List of three phase components Θ_a.
        """
        components = self._phase_components.get_components()
        
        # Convert to CPU if using CUDA
        if self.use_cuda:
            return [self._to_cpu(comp) for comp in components]
        return components
    
    def get_total_phase(self) -> np.ndarray:
        """
        Get the total phase from U(1)³ structure.
        
        Physical Meaning:
            Computes the total phase by combining the three
            U(1) components with proper SU(2) coupling.
            
        Mathematical Foundation:
            Θ_total = Σ_a Θ_a + Σ_{a,b} g_{ab} Θ_a Θ_b
            where g_{ab} are the SU(2) coupling coefficients.
            
        Returns:
            np.ndarray: Total phase field.
        """
        return self._phase_components.get_total_phase(self.coupling_matrix)
    
    def update_phase_components(self, envelope: np.ndarray) -> None:
        """
        Update phase components from solved envelope.
        
        Physical Meaning:
            Updates the three U(1) phase components Θ_a (a=1..3)
            from the solved BVP envelope field.
            
        Mathematical Foundation:
            Extracts phase components from the envelope solution
            and updates the U(1)³ phase structure.
            
        Args:
            envelope (np.ndarray): Solved BVP envelope in 7D space-time.
        """
        self._phase_components.update_components(envelope)
    
    def decompose_phase_structure(self, envelope: np.ndarray = None) -> tuple:
        """
        Decompose phase structure into amplitude and phases.
        
        Physical Meaning:
            Decomposes the BVP field into amplitude and three phase components
            according to the U(1)³ structure: a = |a|e^(iφ₁)e^(iφ₂)e^(iφ₃)
            
        Mathematical Foundation:
            Extracts amplitude |a| and phases φ₁, φ₂, φ₃ from the field
            such that a = |a| * exp(i * (φ₁ + φ₂ + φ₃))
            
        Args:
            envelope (np.ndarray, optional): BVP envelope field. If None, uses current phase components.
            
        Returns:
            tuple: (amplitude, phases) where:
                - amplitude: Field amplitude |a|
                - phases: List of three phase components [φ₁, φ₂, φ₃]
        """
        if envelope is not None:
            # Extract amplitude from envelope
            amplitude = np.abs(envelope)
            
            # Extract phases from envelope
            total_phase = np.angle(envelope)
            
            # Distribute total phase among three U(1) components
            phases = []
            for a in range(3):
                # Each component gets a portion of the total phase
                phase_portion = total_phase / 3.0 + 2 * np.pi * a / 3.0
                phases.append(phase_portion)
        else:
            # Use current phase components
            phase_components = self._phase_components.get_components()
            amplitude = np.abs(phase_components[0])  # Use first component for amplitude
            
            # Extract phases from components
            phases = []
            for theta_a in phase_components:
                phases.append(np.angle(theta_a))
        
        return amplitude, phases
    
    def compute_phase_coherence(self) -> np.ndarray:
        """
        Compute phase coherence measure.
        
        Physical Meaning:
            Computes a measure of phase coherence across the
            U(1)³ structure, indicating the degree of
            synchronization between the three phase components.
            
        Mathematical Foundation:
            Coherence = |Σ_a exp(iΘ_a)| / 3
            where the magnitude indicates coherence strength.
            
        Returns:
            np.ndarray: Phase coherence measure.
        """
        return self._phase_components.compute_phase_coherence()

