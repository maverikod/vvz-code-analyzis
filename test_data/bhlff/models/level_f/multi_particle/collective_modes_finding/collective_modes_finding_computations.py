"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Computation helper methods for collective modes finding.

This module provides computation helper methods as a mixin class.
"""

import numpy as np


class CollectiveModesFindingComputationsMixin:
    """Mixin providing computation helper methods."""
    
    def _compute_mode_interaction_strength(self, eigenvalues: np.ndarray) -> float:
        """
        Compute mode interaction strength from eigenvalues using vectorized processing.
        
        Physical Meaning:
            Computes interaction strength between modes based on
            eigenvalue analysis and 7D phase field theory using vectorized operations.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            
        Returns:
            float: Mode interaction strength.
        """
        try:
            if len(eigenvalues) < 2:
                return 0.0
            
            # Use vectorized processor if available
            if self.vectorized_processor is not None:
                # Vectorized eigenvalue analysis
                sorted_eigenvalues = (
                    self.vectorized_processor.sort_eigenvalues_vectorized(eigenvalues)
                )
                spacing = (
                    self.vectorized_processor.compute_eigenvalue_spacing_vectorized(
                        sorted_eigenvalues
                    )
                )
                
                # Vectorized statistical analysis
                mean_spacing = self.vectorized_processor.compute_mean_vectorized(
                    spacing
                )
                std_spacing = self.vectorized_processor.compute_std_vectorized(spacing)
            else:
                # Standard numpy operations
                sorted_eigenvalues = np.sort(eigenvalues)
                spacing = np.diff(sorted_eigenvalues)
                mean_spacing = np.mean(spacing)
                std_spacing = np.std(spacing)
            
            # Interaction strength based on spacing
            if std_spacing > 1e-10:
                interaction_strength = mean_spacing / std_spacing
            else:
                interaction_strength = 0.0
            
            return float(interaction_strength)
            
        except Exception as e:
            self.logger.error(f"Mode interaction strength computation failed: {e}")
            return 0.0
    
    def _compute_mode_resonance_effects(self, eigenvalues: np.ndarray) -> float:
        """
        Compute mode resonance effects from eigenvalues.
        
        Physical Meaning:
            Computes resonance effects between modes based on
            eigenvalue analysis and 7D phase field theory.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            
        Returns:
            float: Mode resonance effects.
        """
        try:
            if len(eigenvalues) < 2:
                return 0.0
            
            # Compute resonance effects
            sorted_eigenvalues = np.sort(eigenvalues)
            resonance_effects = []
            
            for i in range(len(sorted_eigenvalues) - 1):
                for j in range(i + 1, len(sorted_eigenvalues)):
                    # Compute resonance between modes i and j
                    resonance = abs(sorted_eigenvalues[i] - sorted_eigenvalues[j])
                    resonance_effects.append(resonance)
            
            if resonance_effects:
                mean_resonance = np.mean(resonance_effects)
                return float(mean_resonance)
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Mode resonance effects computation failed: {e}")
            return 0.0
    
    def _compute_mode_mixing_degree(self, eigenvectors: np.ndarray) -> float:
        """
        Compute mode mixing degree from eigenvectors using vectorized processing.
        
        Physical Meaning:
            Computes mixing degree between modes based on
            eigenvector analysis and 7D phase field theory using vectorized operations.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Mode mixing degree.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Use vectorized processor if available
            if self.vectorized_processor is not None:
                # Vectorized eigenvector mixing analysis
                mixing_degrees = (
                    self.vectorized_processor.compute_eigenvector_mixing_vectorized(
                        eigenvectors
                    )
                )
                mean_mixing = self.vectorized_processor.compute_mean_vectorized(
                    mixing_degrees
                )
            else:
                # Standard numpy operations
                mixing_degrees = []
                for i in range(eigenvectors.shape[1]):
                    for j in range(i + 1, eigenvectors.shape[1]):
                        # Compute mixing between modes i and j
                        mixing = np.abs(np.dot(eigenvectors[:, i], eigenvectors[:, j]))
                        mixing_degrees.append(mixing)
                
                if mixing_degrees:
                    mean_mixing = np.mean(mixing_degrees)
                else:
                    mean_mixing = 0.0
            
            return float(mean_mixing)
            
        except Exception as e:
            self.logger.error(f"Mode mixing degree computation failed: {e}")
            return 0.0
    
    def _compute_mode_coherence(self, eigenvectors: np.ndarray) -> float:
        """
        Compute mode coherence from eigenvectors.
        
        Physical Meaning:
            Computes coherence between modes based on
            eigenvector analysis and 7D phase field theory.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Mode coherence.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Compute coherence
            coherences = []
            for i in range(eigenvectors.shape[1]):
                for j in range(i + 1, eigenvectors.shape[1]):
                    # Compute coherence between modes i and j
                    coherence = np.abs(np.dot(eigenvectors[:, i], eigenvectors[:, j]))
                    coherences.append(coherence)
            
            if coherences:
                mean_coherence = np.mean(coherences)
                return float(mean_coherence)
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Mode coherence computation failed: {e}")
            return 0.0
    
    def _compute_mode_interaction_strength_from_eigenvectors(
        self, eigenvectors: np.ndarray
    ) -> float:
        """
        Compute mode interaction strength from eigenvectors.
        
        Physical Meaning:
            Computes interaction strength between modes based on
            eigenvector analysis and 7D phase field theory.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Mode interaction strength.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Compute interaction strength
            interaction_strengths = []
            for i in range(eigenvectors.shape[1]):
                for j in range(i + 1, eigenvectors.shape[1]):
                    # Compute interaction between modes i and j
                    interaction = np.abs(np.dot(eigenvectors[:, i], eigenvectors[:, j]))
                    interaction_strengths.append(interaction)
            
            if interaction_strengths:
                mean_interaction = np.mean(interaction_strengths)
                return float(mean_interaction)
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Mode interaction strength computation failed: {e}")
            return 0.0
    
    def _compute_mode_phase_coherence(self, eigenvectors: np.ndarray) -> float:
        """
        Compute mode phase coherence from eigenvectors.
        
        Physical Meaning:
            Computes phase coherence between modes based on
            eigenvector analysis and 7D phase field theory.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Mode phase coherence.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Compute phase coherence
            phase_coherences = []
            for i in range(eigenvectors.shape[1]):
                for j in range(i + 1, eigenvectors.shape[1]):
                    # Compute phase coherence between modes i and j
                    phase_coherence = np.abs(
                        np.dot(eigenvectors[:, i], eigenvectors[:, j])
                    )
                    phase_coherences.append(phase_coherence)
            
            if phase_coherences:
                mean_phase_coherence = np.mean(phase_coherences)
                return float(mean_phase_coherence)
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Mode phase coherence computation failed: {e}")
            return 0.0
    
    def _compute_distance_coupling_factor(self, distance: float) -> float:
        """
        Compute distance coupling factor.
        
        Physical Meaning:
            Computes coupling factor based on distance using
            7D phase field theory principles.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Distance coupling factor.
        """
        try:
            # Distance-dependent coupling
            coupling_factor = 1.0 / (1.0 + distance**2)
            return float(coupling_factor)
            
        except Exception as e:
            self.logger.error(f"Distance coupling factor computation failed: {e}")
            return 0.0
    
    def _compute_phase_coherence_factor(self, distance: float) -> float:
        """
        Compute phase coherence factor.
        
        Physical Meaning:
            Computes phase coherence factor based on distance using
            7D phase field theory principles.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Phase coherence factor.
        """
        try:
            # Phase coherence based on distance using step function
            phase_coherence = self._step_resonator_phase_coherence(distance)
            return float(phase_coherence)
            
        except Exception as e:
            self.logger.error(f"Phase coherence factor computation failed: {e}")
            return 0.0
    
    def _compute_energy_exchange_factor(self, distance: float) -> float:
        """
        Compute energy exchange factor.
        
        Physical Meaning:
            Computes energy exchange factor based on distance using
            7D phase field theory principles.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Energy exchange factor.
        """
        try:
            # Energy exchange based on distance
            energy_exchange = 1.0 / (1.0 + distance**1.5)
            return float(energy_exchange)
            
        except Exception as e:
            self.logger.error(f"Energy exchange factor computation failed: {e}")
            return 0.0

