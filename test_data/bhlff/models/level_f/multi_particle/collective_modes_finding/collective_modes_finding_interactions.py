"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Interaction computation methods for collective modes finding.

This module provides interaction computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class CollectiveModesFindingInteractionsMixin:
    """Mixin providing interaction computation methods."""
    
    def _calculate_mode_coupling(
        self, eigenvalues: np.ndarray, eigenvectors: np.ndarray
    ) -> float:
        """
        Calculate mode coupling using full analytical method.
        
        Physical Meaning:
            Calculates coupling between collective modes using complete
            analytical methods based on 7D phase field theory.
            
        Mathematical Foundation:
            Implements full mode coupling analysis using eigenvalue
            analysis, mode overlap, and interaction strength.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Comprehensive mode coupling measure.
        """
        try:
            if len(eigenvalues) < 2:
                return 0.0
            
            # Sort eigenvalues for analysis
            sorted_eigenvalues = np.sort(eigenvalues)
            
            # Calculate eigenvalue differences
            eigenvalue_differences = np.diff(sorted_eigenvalues)
            
            # Compute coupling strength based on eigenvalue spacing
            mean_spacing = np.mean(eigenvalue_differences)
            std_spacing = np.std(eigenvalue_differences)
            
            # Avoid division by zero
            if std_spacing > 1e-10:
                coupling_strength = mean_spacing / std_spacing
            else:
                coupling_strength = 0.0
            
            # Compute mode interaction strength
            interaction_strength = self._compute_mode_interaction_strength(eigenvalues)
            
            # Compute mode resonance effects
            resonance_effects = self._compute_mode_resonance_effects(eigenvalues)
            
            # Combine coupling measures
            total_coupling = (
                coupling_strength * interaction_strength * resonance_effects
            )
            
            # Normalize coupling measure
            normalized_coupling = min(1.0, max(0.0, total_coupling))
            
            return float(normalized_coupling)
            
        except Exception as e:
            self.logger.error(f"Mode coupling calculation failed: {e}")
            return 0.0
    
    def _calculate_mode_overlap(self, eigenvectors: np.ndarray) -> float:
        """
        Calculate mode overlap using full analytical method.
        
        Physical Meaning:
            Calculates overlap between collective modes using complete
            analytical methods based on 7D phase field theory.
            
        Mathematical Foundation:
            Implements full mode overlap analysis using eigenvector
            orthogonality, mode mixing, and interaction strength.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Comprehensive mode overlap measure.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Normalize eigenvectors
            normalized_eigenvectors = eigenvectors / np.linalg.norm(
                eigenvectors, axis=0
            )
            
            # Calculate pairwise overlaps
            overlaps = []
            for i in range(normalized_eigenvectors.shape[1]):
                for j in range(i + 1, normalized_eigenvectors.shape[1]):
                    # Compute overlap between modes i and j
                    overlap = np.abs(
                        np.dot(
                            normalized_eigenvectors[:, i], normalized_eigenvectors[:, j]
                        )
                    )
                    overlaps.append(overlap)
            
            if not overlaps:
                return 0.0
            
            # Compute statistical measures of overlap
            mean_overlap = np.mean(overlaps)
            std_overlap = np.std(overlaps)
            max_overlap = np.max(overlaps)
            
            # Compute mode mixing degree
            mixing_degree = self._compute_mode_mixing_degree(normalized_eigenvectors)
            
            # Compute mode coherence
            coherence = self._compute_mode_coherence(normalized_eigenvectors)
            
            # Combine overlap measures
            total_overlap = mean_overlap * mixing_degree * coherence
            
            # Normalize overlap measure
            normalized_overlap = min(1.0, max(0.0, total_overlap))
            
            return float(normalized_overlap)
            
        except Exception as e:
            self.logger.error(f"Mode overlap calculation failed: {e}")
            return 0.0
    
    def _calculate_mode_correlation(self, eigenvectors: np.ndarray) -> float:
        """
        Calculate mode correlation.
        
        Physical Meaning:
            Calculates correlation between collective modes
            based on eigenvectors.
            
        Args:
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            float: Mode correlation measure.
        """
        try:
            if eigenvectors.shape[1] < 2:
                return 0.0
            
            # Normalize eigenvectors
            normalized_eigenvectors = eigenvectors / np.linalg.norm(
                eigenvectors, axis=0
            )
            
            # Calculate pairwise correlations
            correlations = []
            for i in range(normalized_eigenvectors.shape[1]):
                for j in range(i + 1, normalized_eigenvectors.shape[1]):
                    # Compute correlation between modes i and j
                    correlation = np.corrcoef(
                        normalized_eigenvectors[:, i], normalized_eigenvectors[:, j]
                    )[0, 1]
                    if not np.isnan(correlation):
                        correlations.append(correlation)
            
            if not correlations:
                return 0.0
            
            # Compute statistical measures of correlation
            mean_correlation = np.mean(correlations)
            std_correlation = np.std(correlations)
            max_correlation = np.max(correlations)
            
            # Compute mode interaction strength
            interaction_strength = (
                self._compute_mode_interaction_strength_from_eigenvectors(
                    normalized_eigenvectors
                )
            )
            
            # Compute mode phase coherence
            phase_coherence = self._compute_mode_phase_coherence(
                normalized_eigenvectors
            )
            
            # Combine correlation measures
            total_correlation = (
                mean_correlation * interaction_strength * phase_coherence
            )
            
            # Normalize correlation measure
            normalized_correlation = min(1.0, max(0.0, total_correlation))
            
            return float(normalized_correlation)
            
        except Exception as e:
            self.logger.error(f"Mode correlation calculation failed: {e}")
            return 0.0
    
    def _calculate_interaction_strength(self, distance: float) -> float:
        """
        Calculate interaction strength.
        
        Physical Meaning:
            Calculates interaction strength between particles
            based on distance.
            
        Args:
            distance (float): Distance between particles.
            
        Returns:
            float: Interaction strength.
        """
        try:
            if distance <= 0:
                return 1.0
            
            # Base interaction strength from distance
            base_strength = 1.0 / (1.0 + distance)
            
            # Distance-dependent coupling factor
            coupling_factor = self._compute_distance_coupling_factor(distance)
            
            # Phase coherence factor
            phase_coherence = self._compute_phase_coherence_factor(distance)
            
            # Energy exchange factor
            energy_exchange = self._compute_energy_exchange_factor(distance)
            
            # Combine interaction factors
            total_strength = (
                base_strength * coupling_factor * phase_coherence * energy_exchange
            )
            
            # Normalize interaction strength
            normalized_strength = min(1.0, max(0.0, total_strength))
            
            return float(normalized_strength)
            
        except Exception as e:
            self.logger.error(f"Interaction strength calculation failed: {e}")
            return 0.0

