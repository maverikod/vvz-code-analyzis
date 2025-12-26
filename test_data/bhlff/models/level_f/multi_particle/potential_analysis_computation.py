"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Potential analysis computation module.

This module implements potential computation functionality for multi-particle systems
in Level F of 7D phase field theory.

Physical Meaning:
    Computes effective potentials for multi-particle systems
    including single-particle, pair-wise, and higher-order interactions.

Example:
    >>> potential_computer = PotentialComputationAnalyzer(domain, particles, system_params)
    >>> potential = potential_computer.compute_effective_potential()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import Particle, SystemParameters
from .potential_computation_step import StepResonatorPotentialFunctions
from .potential_computation_single import SingleParticlePotentialComputation
from .potential_computation_pair import PairInteractionPotentialComputation
from .potential_computation_higher_order import HigherOrderInteractionComputation


class PotentialComputationAnalyzer:
    """
    Potential computation analyzer for multi-particle systems.

    Physical Meaning:
        Computes effective potentials for multi-particle systems
        including single-particle, pair-wise, and higher-order interactions.

    Mathematical Foundation:
        Implements potential computation:
        - Effective potential: U_eff = Σᵢ Uᵢ + Σᵢ<ⱼ Uᵢⱼ + Σᵢ<ⱼ<ₖ Uᵢⱼₖ
        - Single-particle potential: Uᵢ = U₀(x - xᵢ)
        - Pair-wise potential: Uᵢⱼ = U₁(|xᵢ - xⱼ|)
    """

    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize potential computation analyzer.

        Physical Meaning:
            Sets up the potential computation system with
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

        # Initialize step resonator potential functions
        self.step_potentials = StepResonatorPotentialFunctions(system_params)
        
        # Initialize specialized computation classes
        self.single_computation = SingleParticlePotentialComputation(
            domain, system_params, self.step_potentials.step_interaction_potential
        )
        self.pair_computation = PairInteractionPotentialComputation(
            domain,
            system_params,
            self.step_potentials.step_three_body_interaction_potential,
        )
        self.higher_order_computation = HigherOrderInteractionComputation(
            domain,
            system_params,
            self.step_potentials.step_three_particle_interaction_potential,
        )

        # Initialize potential analysis
        self._initialize_potential_analysis()

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
        self.logger.info("Computing effective potential")

        # Initialize potential
        potential = np.zeros(self.domain.shape)

        # Add single-particle potentials
        for particle in self.particles:
            single_potential = self.single_computation.compute_single_particle_potential(
                particle
            )
            potential += single_potential

        # Add pair-wise interactions
        for i, particle_i in enumerate(self.particles):
            for j, particle_j in enumerate(self.particles[i + 1 :], i + 1):
                pair_potential = self.pair_computation.compute_pair_interaction(
                    particle_i, particle_j
                )
                potential += pair_potential

        # Add higher-order interactions
        higher_order_potential = (
            self.higher_order_computation.compute_higher_order_interactions(
                self.particles
            )
        )
        potential += higher_order_potential

        self.logger.info("Effective potential computed")
        return potential

    def _initialize_potential_analysis(self) -> None:
        """
        Initialize potential analysis.

        Physical Meaning:
            Initializes potential analysis system with
            appropriate parameters and methods.
        """
        # Setup interaction matrices
        self._setup_interaction_matrices()

        # Setup potential functions
        self._setup_potential_functions()

    def _setup_interaction_matrices(self) -> None:
        """
        Setup interaction matrices.

        Physical Meaning:
            Sets up interaction matrices for multi-particle system
            to enable efficient potential calculations.
        """
        # Setup interaction matrices
        # In practice, this would involve proper matrix setup
        self.interaction_matrix = np.zeros((len(self.particles), len(self.particles)))

        # Calculate interaction strengths
        for i, particle_i in enumerate(self.particles):
            for j, particle_j in enumerate(self.particles):
                if i != j:
                    distance = np.linalg.norm(particle_i.position - particle_j.position)
                    interaction_strength = (
                        self.step_potentials.calculate_interaction_strength(distance)
                    )
                    self.interaction_matrix[i, j] = interaction_strength

    def _setup_potential_functions(self) -> None:
        """
        Setup potential functions.

        Physical Meaning:
            Sets up potential functions for multi-particle system
            to enable efficient potential calculations.
        """
        # Setup potential functions
        # In practice, this would involve proper function setup
        self.potential_functions = {
            "single_particle": self.single_computation.create_single_particle_potential,
            "pair_interaction": self.pair_computation.create_pair_potential,
            "higher_order": self.higher_order_computation.create_higher_order_potential,
        }
