"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multi-particle system implementation for Level F collective effects.

This module provides a facade for multi-particle system functionality
for Level F models in 7D phase field theory, ensuring proper functionality
of all multi-particle analysis components.

Theoretical Background:
    Multi-particle systems in 7D phase field theory are described by
    effective potentials that include single-particle, pair-wise, and
    higher-order interactions:
    U_eff = Σᵢ Uᵢ + Σᵢ<ⱼ Uᵢⱼ + Σᵢ<ⱼ<ₖ Uᵢⱼₖ + ...

    Collective modes arise from the diagonalization of the dynamics matrix
    E⁻¹K, where E is the energy matrix and K is the stiffness matrix.

Example:
    >>> particles = [Particle(position=[5,10,10], charge=1, phase=0),
    ...              Particle(position=[15,10,10], charge=-1, phase=π)]
    >>> system = MultiParticleSystem(domain, particles)
    >>> potential = system.compute_effective_potential()
    >>> modes = system.find_collective_modes()
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from ..base.abstract_model import AbstractModel
from .multi_particle.data_structures import Particle, SystemParameters
from .multi_particle_potential import MultiParticlePotentialAnalyzer
from .multi_particle_modes import MultiParticleModesAnalyzer
from .multi_particle_analysis import MultiParticleSystemAnalyzer


class MultiParticleSystem(AbstractModel):
    """
    Multi-particle system for Level F collective effects.

    Physical Meaning:
        Studies collective effects in systems with multiple
        topological defects, including effective potential
        calculations and collective mode analysis.

    Mathematical Foundation:
        Implements multi-particle system analysis:
        - Effective potential: U_eff = Σᵢ Uᵢ + Σᵢ<ⱼ Uᵢⱼ + Σᵢ<ⱼ<ₖ Uᵢⱼₖ
        - Collective modes: diagonalization of M⁻¹K
        - Correlation functions: G(x,t) = ⟨ψ*(x,t)ψ(0,0)⟩
    """

    def __init__(
        self,
        domain,
        particles: List[Particle],
        interaction_range: float = 2.0,
        system_params: Optional[SystemParameters] = None,
    ):
        """
        Initialize multi-particle system.

        Physical Meaning:
            Sets up the multi-particle system with particles and
            interaction parameters for collective effects analysis.

        Args:
            domain: Domain parameters.
            particles (List[Particle]): List of particles.
            interaction_range (float): Interaction range parameter.
            system_params (Optional[SystemParameters]): System parameters.
        """
        super().__init__()
        self.domain = domain
        self.particles = particles
        self.interaction_range = interaction_range
        self.system_params = system_params or SystemParameters()

        # Initialize analysis components
        self._potential_analyzer = MultiParticlePotentialAnalyzer(
            domain, particles, interaction_range
        )
        self._modes_analyzer = MultiParticleModesAnalyzer(
            domain, particles, interaction_range
        )
        self._system_analyzer = MultiParticleSystemAnalyzer(
            domain, particles, interaction_range
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
        return self._potential_analyzer.compute_effective_potential()

    def find_collective_modes(self) -> Dict[str, Any]:
        """
        Find collective modes.

        Physical Meaning:
            Finds collective modes in multi-particle system
            through diagonalization of dynamics matrix.

        Mathematical Foundation:
            Collective modes: diagonalization of E⁻¹K
            where E is the energy matrix and K is the stiffness matrix.

        Returns:
            Dict[str, Any]: Collective modes analysis results.
        """
        return self._modes_analyzer.find_collective_modes()

    def compute_correlation_function(
        self, field: np.ndarray, time_points: np.ndarray
    ) -> np.ndarray:
        """
        Compute correlation function.

        Physical Meaning:
            Computes correlation function for multi-particle system
            to analyze collective behavior.

        Mathematical Foundation:
            Correlation function: G(x,t) = ⟨ψ*(x,t)ψ(0,0)⟩

        Args:
            field (np.ndarray): Field configuration.
            time_points (np.ndarray): Time points for correlation.

        Returns:
            np.ndarray: Correlation function.
        """
        return self._modes_analyzer.compute_correlation_function(field, time_points)

    def analyze_system_properties(self) -> Dict[str, Any]:
        """
        Analyze system properties.

        Physical Meaning:
            Analyzes system properties including energy, stability,
            and optimization for multi-particle system.

        Mathematical Foundation:
            Analyzes system properties through:
            - System energy: E = ∫ U_eff(x) dx
            - System stability: analysis of collective modes
            - System optimization: parameter optimization

        Returns:
            Dict[str, Any]: System properties analysis results.
        """
        return self._system_analyzer.analyze_system_properties()
