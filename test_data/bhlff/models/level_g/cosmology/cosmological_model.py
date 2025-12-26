"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main cosmological model for 7D phase field theory.

This module implements the main cosmological model that
coordinates the evolution of phase fields in expanding universe.

Theoretical Background:
    The cosmological evolution module implements the time evolution
    of phase fields in expanding spacetime, where the phase field
    represents the fundamental field that drives structure formation.

Mathematical Foundation:
    Solves the phase field evolution equation in expanding spacetime:
    ∂²a/∂t² + 3H(t)∂a/∂t - c_φ²∇²a + V'(a) = 0

Example:
    >>> model = CosmologicalModel(initial_conditions, params)
    >>> evolution = model.evolve_universe([0, 13.8])
"""

import numpy as np
from typing import Dict, Any, List, Optional
from ...base.model_base import ModelBase
from .envelope_effective_metric import EnvelopeEffectiveMetric
from .phase_field_evolution import PhaseFieldEvolution
from .structure_formation import StructureFormation
from .cosmological_parameters import CosmologicalParameters


class CosmologicalModel(ModelBase):
    """
    Main cosmological evolution model for 7D phase field theory.

    Physical Meaning:
        Implements the evolution of phase field in expanding universe,
        including structure formation and cosmological parameters.

    Mathematical Foundation:
        Solves the phase field evolution equation in expanding spacetime:
        ∂²a/∂t² + 3H(t)∂a/∂t - c_φ²∇²a + V'(a) = 0

    Attributes:
        scale_factor (np.ndarray): Scale factor evolution a(t)
        hubble_parameter (np.ndarray): Hubble parameter H(t)
        phase_field (np.ndarray): Phase field configuration
        cosmology_params (dict): Cosmological parameters
    """

    def __init__(
        self, initial_conditions: Dict[str, Any], cosmology_params: Dict[str, Any]
    ):
        """
        Initialize cosmological model.

        Physical Meaning:
            Sets up the cosmological model with initial conditions
            and cosmological parameters for universe evolution.

        Args:
            initial_conditions: Initial phase field configuration
            cosmology_params: Cosmological parameters
        """
        super().__init__()
        self.initial_conditions = initial_conditions
        self.cosmology_params = cosmology_params

        # Initialize specialized components
        self.metric = EnvelopeEffectiveMetric(cosmology_params)
        self.phase_field_evolution = PhaseFieldEvolution(cosmology_params)
        self.structure_formation = StructureFormation(cosmology_params)
        self.cosmological_parameters = CosmologicalParameters(cosmology_params)

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

        # Initialize arrays
        self.time_steps = np.arange(self.time_start, self.time_end + self.dt, self.dt)
        self.scale_factor = np.zeros_like(
            self.time_steps
        )  # Will be filled during evolution
        self.hubble_parameter = np.zeros_like(
            self.time_steps
        )  # Will be filled during evolution
        self.phase_field = None

    def evolve_universe(
        self, time_range: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Evolve universe from initial to final time.

        Physical Meaning:
            Evolves the universe from initial conditions through
            cosmological time, computing phase field evolution
            and structure formation.

        Mathematical Foundation:
            Integrates the phase field evolution equation with
            cosmological expansion and gravitational effects.

        Args:
            time_range: Optional time range [start, end]

        Returns:
            Dictionary with evolution results
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
        }

        # Time evolution
        for i, t in enumerate(self.time_steps):
            # Update scale factor
            # Use envelope effective metric for scale factors
            a_t = self.metric.compute_scale_factor(t)
            self.scale_factor[i] = a_t
            self.hubble_parameter[i] = (
                self.cosmological_parameters.compute_hubble_parameter(t)
            )

            # Evolve phase field
            if i == 0:
                # Initial conditions
                self.phase_field = self.phase_field_evolution.initialize_phase_field(
                    self.initial_conditions
                )
            else:
                # Evolution step
                self.phase_field = self.phase_field_evolution.evolve_phase_field_step(
                    self.phase_field, t, self.dt, a_t
                )

            # Analyze structure
            structure = self.structure_formation.analyze_structure_at_time(
                t, self.phase_field
            )

            evolution_results["phase_field_evolution"].append(self.phase_field.copy())
            evolution_results["structure_formation"].append(structure)

        # Add scale factor and Hubble parameter to results
        evolution_results["scale_factor"] = self.scale_factor.copy()
        evolution_results["hubble_parameter"] = self.hubble_parameter.copy()

        return evolution_results

    def analyze_structure_formation(self) -> Dict[str, Any]:
        """
        Analyze large-scale structure formation.

        Physical Meaning:
            Analyzes the overall process of structure formation
            throughout cosmological evolution.

        Returns:
            Structure formation analysis
        """
        if not hasattr(self, "scale_factor") or len(self.scale_factor) == 0:
            return {}

        # Analyze structure formation metrics
        analysis = {
            "total_evolution_time": self.time_end - self.time_start,
            "final_scale_factor": self.scale_factor[-1],
            "expansion_rate": np.mean(np.diff(self.scale_factor) / self.dt),
            "structure_growth_rate": self._compute_structure_growth_rate(),
        }

        return analysis

    def _compute_structure_growth_rate(self) -> float:
        """
        Compute structure growth rate.

        Physical Meaning:
            Computes the rate at which large-scale structure
            grows during cosmological evolution.

        Returns:
            Structure growth rate
        """
        if not hasattr(self, "scale_factor") or len(self.scale_factor) < 2:
            return 0.0

        # Use structure formation component
        phase_field_evolution = getattr(self, "phase_field_evolution", [])
        if hasattr(self, "phase_field") and self.phase_field is not None:
            phase_field_evolution = [self.phase_field]

        growth_rate = self.structure_formation.compute_structure_growth_rate(
            self.scale_factor, phase_field_evolution
        )

        return growth_rate

    def compute_cosmological_parameters(self) -> Dict[str, float]:
        """
        Compute cosmological parameters from evolution.

        Physical Meaning:
            Computes derived cosmological parameters from
            the evolution results.

        Returns:
            Dictionary of cosmological parameters
        """
        if not hasattr(self, "scale_factor") or len(self.scale_factor) == 0:
            return {}

        # Use cosmological parameters component
        parameters = self.cosmological_parameters.compute_cosmological_parameters(
            self.scale_factor, self.hubble_parameter, self.time_end
        )

        return parameters
