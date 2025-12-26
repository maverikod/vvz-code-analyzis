"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Analysis methods for collective modes finding.

This module provides mode analysis methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class CollectiveModesFindingAnalysisMixin:
    """Mixin providing mode analysis methods."""
    
    def _analyze_collective_modes(
        self, eigenvalues: np.ndarray, eigenvectors: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze collective modes.
        
        Physical Meaning:
            Analyzes collective modes from eigenvalues and eigenvectors
            of dynamics matrix.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            Dict[str, Any]: Collective modes analysis results.
        """
        # Analyze mode stability
        stability_analysis = self._analyze_mode_stability(eigenvalues)
        
        # Analyze mode interactions
        interaction_analysis = self._analyze_mode_interactions(
            eigenvalues, eigenvectors
        )
        
        # Calculate mode statistics
        mode_statistics = {
            "num_modes": len(eigenvalues),
            "stable_modes": np.sum(eigenvalues.real < 0),
            "unstable_modes": np.sum(eigenvalues.real > 0),
            "oscillatory_modes": np.sum(eigenvalues.imag != 0),
        }
        
        return {
            "stability_analysis": stability_analysis,
            "interaction_analysis": interaction_analysis,
            "mode_statistics": mode_statistics,
        }
    
    def _analyze_mode_stability(self, eigenvalues: np.ndarray) -> Dict[str, Any]:
        """
        Analyze mode stability.
        
        Physical Meaning:
            Analyzes stability of collective modes
            based on eigenvalues.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            
        Returns:
            Dict[str, Any]: Mode stability analysis results.
        """
        # Analyze stability based on eigenvalues
        real_parts = eigenvalues.real
        imaginary_parts = eigenvalues.imag
        
        # Calculate stability metrics
        stability_metrics = {
            "stable_modes": np.sum(real_parts < 0),
            "unstable_modes": np.sum(real_parts > 0),
            "marginal_modes": np.sum(real_parts == 0),
            "oscillatory_modes": np.sum(imaginary_parts != 0),
            "damping_ratio": np.mean(np.abs(real_parts) / np.abs(eigenvalues)),
        }
        
        return stability_metrics
    
    def _analyze_mode_interactions(
        self, eigenvalues: np.ndarray, eigenvectors: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze mode interactions.
        
        Physical Meaning:
            Analyzes interactions between collective modes
            based on eigenvalues and eigenvectors.
            
        Args:
            eigenvalues (np.ndarray): Eigenvalues of dynamics matrix.
            eigenvectors (np.ndarray): Eigenvectors of dynamics matrix.
            
        Returns:
            Dict[str, Any]: Mode interaction analysis results.
        """
        # Calculate mode coupling
        mode_coupling = self._calculate_mode_coupling(eigenvalues, eigenvectors)
        
        # Calculate mode overlap
        mode_overlap = self._calculate_mode_overlap(eigenvectors)
        
        # Calculate mode correlation
        mode_correlation = self._calculate_mode_correlation(eigenvectors)
        
        return {
            "mode_coupling": mode_coupling,
            "mode_overlap": mode_overlap,
            "mode_correlation": mode_correlation,
        }

