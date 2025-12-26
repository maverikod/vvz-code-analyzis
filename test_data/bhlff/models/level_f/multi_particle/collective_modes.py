"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Collective modes analysis module for multi-particle systems.

This module implements collective modes analysis functionality
for Level F models in 7D phase field theory.

Physical Meaning:
    Implements collective modes analysis including mode finding,
    stability analysis, and mode interactions.

Example:
    >>> analyzer = CollectiveModesAnalyzer(domain, particles, system_params)
    >>> modes = analyzer.find_collective_modes()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from scipy.linalg import eig
from bhlff.models.base.abstract_model import AbstractModel
from .data_structures import Particle, SystemParameters
from .collective_modes_finding import CollectiveModesFinder
from .collective_modes_spectrum import CollectiveModesSpectrumAnalyzer


class CollectiveModesAnalyzer(AbstractModel):
    """
    Collective modes analysis for multi-particle systems.

    Physical Meaning:
        Analyzes collective modes in multi-particle systems,
        including mode finding, stability analysis, and
        mode interactions.

    Mathematical Foundation:
        Implements collective modes analysis methods:
        - Mode finding: diagonalization of dynamics matrix M⁻¹K
        - Stability analysis: eigenvalue analysis
        - Mode interactions: coupling analysis
    """

    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize collective modes analyzer.

        Physical Meaning:
            Sets up the collective modes analysis system with
            domain, particles, and system parameters.

        Args:
            domain: Domain parameters.
            particles (List[Particle]): List of particles.
            system_params (SystemParameters): System parameters.
        """
        super().__init__()
        self.domain = domain
        self.particles = particles
        self.system_params = system_params

        # Initialize analysis components
        self._modes_finder = CollectiveModesFinder(domain, particles, system_params)
        self._spectrum_analyzer = CollectiveModesSpectrumAnalyzer(
            domain, particles, system_params
        )

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
        return self._modes_finder.find_collective_modes()

    def analyze_mode_spectrum(self, modes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze mode spectrum.

        Physical Meaning:
            Analyzes mode spectrum including frequency distribution,
            spectral features, and mode spacing.

        Mathematical Foundation:
            Analyzes mode spectrum through:
            - Frequency distribution analysis
            - Spectral features analysis
            - Mode spacing analysis

        Args:
            modes (Dict[str, Any]): Collective modes analysis results.

        Returns:
            Dict[str, Any]: Mode spectrum analysis results.
        """
        return self._spectrum_analyzer.analyze_mode_spectrum(modes)
