"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for collective modes finding.

This module provides the base CollectiveModesFinderBase class with common
initialization and main find_collective_modes method.
"""

import numpy as np
from typing import Dict, Any, List
import logging
from scipy.linalg import eig

from bhlff.core.domain.vectorized_7d_processor import Vectorized7DProcessor
from ..data_structures import Particle, SystemParameters


class CollectiveModesFinderBase:
    """
    Base class for collective modes finding.
    
    Physical Meaning:
        Provides base functionality for finding collective modes in
        multi-particle systems through diagonalization of dynamics matrix.
        
    Mathematical Foundation:
        Implements collective modes finding:
        - Mode finding: diagonalization of dynamics matrix E⁻¹K
        - Dynamics matrix: E⁻¹K where E is energy matrix and K is stiffness matrix
    """
    
    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize collective modes finder.
        
        Physical Meaning:
            Sets up the collective modes finding system with
            domain, particles, and system parameters.
            
        Args:
            domain: Domain parameters.
            particles (List[Particle]): List of particles.
            system_params (SystemParameters): System parameters.
        """
        self.domain = domain
        self.particles = particles
        self.system_params = system_params
        self.logger = logging.getLogger(__name__)
        
        # Initialize vectorized processor for 7D computations
        if domain is not None:
            self.vectorized_processor = Vectorized7DProcessor(
                domain=domain, config=getattr(domain, "config", {})
            )
        else:
            self.vectorized_processor = None
        
        # Initialize collective modes analysis
        self._initialize_collective_modes_analysis()
    
    def find_collective_modes(self) -> Dict[str, Any]:
        """
        Find collective modes.
        
        Physical Meaning:
            Finds collective modes in multi-particle system
            through diagonalization of dynamics matrix.
            
        Mathematical Foundation:
            Mode finding: diagonalization of dynamics matrix E⁻¹K
            where E is the energy matrix and K is the stiffness matrix.
            
        Returns:
            Dict[str, Any]: Collective modes analysis results.
        """
        self.logger.info("Finding collective modes")
        
        # Compute dynamics matrix
        dynamics_matrix = self._compute_dynamics_matrix()
        
        # Diagonalize dynamics matrix
        eigenvalues, eigenvectors = eig(dynamics_matrix)
        
        # Analyze collective modes
        modes_analysis = self._analyze_collective_modes(eigenvalues, eigenvectors)
        
        results = {
            "eigenvalues": eigenvalues,
            "eigenvectors": eigenvectors,
            "dynamics_matrix": dynamics_matrix,
            "modes_analysis": modes_analysis,
            "collective_modes_complete": True,
        }
        
        self.logger.info("Collective modes found")
        return results

