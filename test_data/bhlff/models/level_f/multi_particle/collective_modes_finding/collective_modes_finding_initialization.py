"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Initialization methods for collective modes finding.

This module provides initialization and setup methods as a mixin class.
"""

import logging


class CollectiveModesFindingInitializationMixin:
    """Mixin providing initialization methods."""
    
    def _initialize_collective_modes_analysis(self) -> None:
        """
        Initialize collective modes analysis.
        
        Physical Meaning:
            Initializes collective modes analysis system with
            appropriate parameters and methods.
        """
        # Setup dynamics matrices
        self._setup_dynamics_matrices()
        
        # Setup mode analysis methods
        self._setup_mode_analysis_methods()
    
    def _setup_dynamics_matrices(self) -> None:
        """
        Setup dynamics matrices.
        
        Physical Meaning:
            Sets up dynamics matrices for collective modes analysis
            including energy and stiffness matrices using 7D BVP theory.
        """
        # Setup energy matrix from field configuration
        self.energy_matrix = self._create_energy_matrix()
        
        # Setup stiffness matrix
        self.stiffness_matrix = self._create_stiffness_matrix()
        
        # Setup dynamics matrix E⁻¹K where E is energy matrix
        self.dynamics_matrix = (
            self._compute_energy_matrix_inverse(self.energy_matrix)
            @ self.stiffness_matrix
        )
    
    def _setup_mode_analysis_methods(self) -> None:
        """
        Setup mode analysis methods.
        
        Physical Meaning:
            Sets up mode analysis methods for collective modes
            analysis including stability and interaction analysis.
        """
        # Setup mode analysis methods
        self.mode_analysis_methods = {
            "stability_analysis": self._analyze_mode_stability,
            "interaction_analysis": self._analyze_mode_interactions,
        }

