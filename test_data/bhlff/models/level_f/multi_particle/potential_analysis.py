"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Potential analysis module for multi-particle systems.

This module implements potential analysis functionality
for Level F models in 7D phase field theory.

Physical Meaning:
    Implements potential analysis including effective potential
    computation, interaction analysis, and potential optimization.

Example:
    >>> analyzer = PotentialAnalyzer(domain, particles, system_params)
    >>> potential = analyzer.compute_effective_potential()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from ...base.abstract_model import AbstractModel
from .data_structures import Particle, SystemParameters
from .potential_analysis_computation import PotentialComputationAnalyzer
from .potential_analysis_landscape import PotentialLandscapeAnalyzer
from .potential_analysis_optimization import PotentialOptimizationAnalyzer


class PotentialAnalyzer(AbstractModel):
    """
    Potential analysis for multi-particle systems.

    Physical Meaning:
        Analyzes the effective potential in multi-particle systems,
        including single-particle, pair-wise, and higher-order
        interactions.

    Mathematical Foundation:
        Implements potential analysis methods:
        - Effective potential: U_eff = Σᵢ Uᵢ + Σᵢ<ⱼ Uᵢⱼ + Σᵢ<ⱼ<ₖ Uᵢⱼₖ
        - Single-particle potential: Uᵢ = U₀(x - xᵢ)
        - Pair-wise potential: Uᵢⱼ = U₁(|xᵢ - xⱼ|)
        - Higher-order potential: Uᵢⱼₖ = U₂(xᵢ, xⱼ, xₖ)
    """

    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize potential analyzer.

        Physical Meaning:
            Sets up the potential analysis system with
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
        self._computation_analyzer = PotentialComputationAnalyzer(
            domain, particles, system_params
        )
        self._landscape_analyzer = PotentialLandscapeAnalyzer(
            domain, particles, system_params
        )
        self._optimization_analyzer = PotentialOptimizationAnalyzer(
            domain, particles, system_params
        )

    def compute_effective_potential(self) -> np.ndarray:
        """
        Compute effective potential.

        Physical Meaning:
            Computes effective potential for multi-particle system
            including all interaction terms.

        Mathematical Foundation:
            Effective potential: U_eff = Σᵢ Uᵢ + Σᵢ<ⱼ Uᵢⱼ + Σᵢ<ⱼ<ₖ Uᵢⱼₖ

        Returns:
            np.ndarray: Effective potential field.
        """
        return self._computation_analyzer.compute_effective_potential()

    def analyze_potential_landscape(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Analyze potential landscape.

        Physical Meaning:
            Analyzes potential landscape including extrema, barriers, and wells
            for multi-particle system.

        Mathematical Foundation:
            Analyzes potential landscape through:
            - Extrema analysis: finding critical points
            - Barrier analysis: analyzing potential barriers
            - Well analysis: analyzing potential wells

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Potential landscape analysis results.
        """
        return self._landscape_analyzer.analyze_potential_landscape(potential)

    def optimize_potential(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Optimize potential.

        Physical Meaning:
            Optimizes potential configuration to minimize energy
            and improve stability for multi-particle system.

        Mathematical Foundation:
            Optimizes potential through:
            - Energy minimization: min E[U_eff]
            - Stability optimization: max stability[U_eff]
            - Parameter optimization: min f(parameters)

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Potential optimization results.
        """
        return self._optimization_analyzer.optimize_potential(potential)
