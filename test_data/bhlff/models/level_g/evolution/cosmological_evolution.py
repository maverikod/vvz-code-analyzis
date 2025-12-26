"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main cosmological evolution model for 7D phase field theory.

This module implements the main cosmological evolution model that
coordinates the evolution of phase fields in expanding universe.

Theoretical Background:
    The cosmological evolution module implements the time evolution
    of phase fields in expanding spacetime, where the phase field
    represents the fundamental field that drives structure formation.

Mathematical Foundation:
    Integrates the phase field evolution equation with
    cosmological expansion and gravitational effects.

Example:
    >>> evolution = CosmologicalEvolution(initial_conditions, params)
    >>> results = evolution.evolve_cosmology(time_range)
"""

import numpy as np
from typing import Dict, Any, List, Optional
from ...base.model_base import ModelBase
from .phase_field_evolution import PhaseFieldEvolution
from .structure_formation import StructureFormation
from .cosmological_parameters import CosmologicalParameters
from .evolution_analysis import EvolutionAnalysis


class CosmologicalEvolution(ModelBase):
    """
    Main cosmological evolution model for 7D phase field theory.

    Physical Meaning:
        Implements the cosmological evolution of phase fields
        in expanding universe, including structure formation
        and cosmological parameters.

    Mathematical Foundation:
        Integrates the phase field evolution equation with
        cosmological expansion and gravitational effects.

    Attributes:
        initial_conditions (dict): Initial phase field configuration
        cosmology_params (dict): Cosmological parameters
        evolution_results (dict): Evolution results
        time_steps (np.ndarray): Time evolution steps
    """

    def __init__(
        self, initial_conditions: Dict[str, Any], cosmology_params: Dict[str, Any]
    ):
        """
        Initialize cosmological evolution model.

        Physical Meaning:
            Sets up the cosmological evolution model with initial
            conditions and cosmological parameters.

        Args:
            initial_conditions: Initial phase field configuration
            cosmology_params: Cosmological parameters
        """
        super().__init__()
        self.initial_conditions = initial_conditions
        self.cosmology_params = cosmology_params
        self.evolution_results = {}
        self.time_steps = None

        # Initialize specialized components
        self.phase_field_evolution = PhaseFieldEvolution(cosmology_params)
        self.structure_formation = StructureFormation(cosmology_params)
        self.cosmological_parameters = CosmologicalParameters(cosmology_params)
        self.evolution_analysis = EvolutionAnalysis()

        self._setup_evolution_parameters()

    def _setup_evolution_parameters(self) -> None:
        """
        Setup evolution parameters.

        Physical Meaning:
            Initializes parameters for cosmological evolution,
            including time steps and physical constants.
        """
        # Time evolution parameters
        self.time_start = self.cosmology_params.get("time_start", 0.0)
        self.time_end = self.cosmology_params.get("time_end", 13.8)  # Gyr
        self.dt = self.cosmology_params.get("dt", 0.01)  # Gyr

        # Physical parameters
        self.c_phi = self.cosmology_params.get("c_phi", 1e10)  # Phase velocity
        # No phase_mass - removed according to 7D BVP theory
        self.G = self.cosmology_params.get("G", 6.67430e-11)  # Gravitational constant

        # Cosmological parameters
        self.H0 = self.cosmology_params.get("H0", 70.0)  # Hubble constant km/s/Mpc
        self.omega_m = self.cosmology_params.get("omega_m", 0.3)  # Matter density
        self.omega_lambda = self.cosmology_params.get(
            "omega_lambda", 0.7
        )  # Dark energy

        # Domain parameters
        self.domain_size = self.cosmology_params.get("domain_size", 1000.0)  # Mpc
        self.resolution = self.cosmology_params.get("resolution", 256)

        # Initialize time steps
        self.time_steps = np.arange(self.time_start, self.time_end + self.dt, self.dt)

    def evolve_cosmology(
        self, time_range: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Evolve cosmology from initial to final time.

        Physical Meaning:
            Evolves the cosmology from initial conditions through
            cosmological time, computing phase field evolution
            and structure formation.

        Mathematical Foundation:
            Integrates the phase field evolution equation with
            cosmological expansion and gravitational effects.

        Args:
            time_range: Optional time range [start, end]

        Returns:
            Cosmological evolution results
        """
        if time_range is not None:
            self.time_start, self.time_end = time_range
            self.time_steps = np.arange(
                self.time_start, self.time_end + self.dt, self.dt
            )

        # Initialize evolution
        evolution_results = {
            "time": self.time_steps,
            "scale_factor": np.zeros_like(self.time_steps),
            "hubble_parameter": np.zeros_like(self.time_steps),
            "phase_field_evolution": [],
            "structure_formation": [],
            "cosmological_parameters": [],
        }

        # Time evolution
        for i, t in enumerate(self.time_steps):
            # Update cosmological parameters
            scale_factor = self.cosmological_parameters.compute_scale_factor(t)
            hubble_parameter = self.cosmological_parameters.compute_hubble_parameter(t)

            evolution_results["scale_factor"][i] = scale_factor
            evolution_results["hubble_parameter"][i] = hubble_parameter

            # Evolve phase field
            if i == 0:
                # Initial conditions
                phase_field = self.phase_field_evolution.initialize_phase_field(
                    self.initial_conditions
                )
            else:
                # Evolution step
                phase_field = self.phase_field_evolution.evolve_phase_field_step(
                    t, self.dt, scale_factor
                )

            # Analyze structure
            structure = self.structure_formation.analyze_structure_at_time(
                t, phase_field
            )
            cosmological_params = (
                self.cosmological_parameters.compute_cosmological_parameters(
                    t, scale_factor
                )
            )

            evolution_results["phase_field_evolution"].append(phase_field.copy())
            evolution_results["structure_formation"].append(structure)
            evolution_results["cosmological_parameters"].append(cosmological_params)

        self.evolution_results = evolution_results
        return evolution_results

    def analyze_cosmological_evolution(self) -> Dict[str, Any]:
        """
        Analyze cosmological evolution results.

        Physical Meaning:
            Analyzes the overall cosmological evolution process,
            including structure formation and parameter evolution.

        Returns:
            Cosmological evolution analysis
        """
        if not hasattr(self, "evolution_results") or len(self.evolution_results) == 0:
            return {}

        # Use evolution analysis component
        analysis = self.evolution_analysis.analyze_cosmological_evolution(
            self.evolution_results, self.time_start, self.time_end, self.dt
        )

        return analysis
