"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

VBP envelope gravitational effects interface for 7D phase field theory.

This module provides the main interface for gravitational effects,
delegating to specialized modules for envelope curvature calculations,
phase envelope balance equations, and gravitational waves.

Theoretical Background:
    In 7D BVP theory, gravity arises from the curvature of the VBP envelope,
    not from spacetime curvature. The gravitational effects module implements
    the connection between the 7D phase field and gravity through envelope
    dynamics and effective metric g_eff[Θ].

Mathematical Foundation:
    Solves phase envelope balance equation: D[Θ] = source
    where D includes time memory (Γ,K) and spatial (−Δ)^β terms
    with c_φ(a,k), χ/κ bridge

Example:
    >>> gravity = VBPGravitationalEffectsModel(system, gravity_params)
    >>> envelope_result = gravity.compute_envelope_effects()
"""

# Import all gravitational effects classes and functionality
from .gravity_curvature import VBPEnvelopeCurvatureCalculator
from .gravity_einstein import PhaseEnvelopeBalanceSolver
from .gravity_waves import VBPGravitationalWavesCalculator
from ..base.model_base import ModelBase
from typing import Dict, Any, Optional
import numpy as np


class VBPGravitationalEffectsModel(ModelBase):
    """
    Main interface for VBP envelope gravitational effects in 7D phase field theory.

    Physical Meaning:
        Provides the main interface for gravitational effects including
        VBP envelope curvature, phase envelope balance equations, and
        gravitational waves. Gravity arises from envelope curvature,
        not spacetime curvature.

    Mathematical Foundation:
        Coordinates the solution of phase envelope balance equations
        with VBP envelope dynamics and computes all gravitational effects.
    """

    def __init__(self, system: Any, gravity_params: Dict[str, Any]):
        """
        Initialize VBP envelope gravitational effects model.

        Physical Meaning:
            Sets up the gravitational effects model with specialized
            calculators for envelope curvature, phase envelope balance,
            and gravitational waves from VBP dynamics.

        Args:
            system: Phase field system
            gravity_params: Gravitational parameters
        """
        super().__init__()
        self.system = system
        self.gravity_params = gravity_params

        # Initialize specialized calculators
        self.curvature_calc = VBPEnvelopeCurvatureCalculator(
            system.domain, gravity_params
        )
        self.envelope_solver = PhaseEnvelopeBalanceSolver(system.domain, gravity_params)
        self.waves_calc = VBPGravitationalWavesCalculator(system.domain, gravity_params)

        self._setup_gravitational_parameters()

    def _setup_gravitational_parameters(self) -> None:
        """
        Setup VBP envelope gravitational parameters.

        Physical Meaning:
            Initializes gravitational parameters for VBP envelope dynamics
            including phase velocity, bridge parameters, and coupling constants.
        """
        # VBP envelope parameters
        self.c_phi = self.gravity_params.get("c_phi", 1.0)  # Phase velocity
        self.chi_kappa = self.gravity_params.get("chi_kappa", 1.0)  # Bridge parameter
        self.beta = self.gravity_params.get("beta", 0.5)  # Fractional order
        self.mu = self.gravity_params.get("mu", 1.0)  # Diffusion coefficient

        # Stability: assert c_φ^2>0, M_*^2>0 wherever built
        assert self.c_phi**2 > 0, f"Stability violation: c_φ^2 = {self.c_phi**2} ≤ 0"
        assert self.mu > 0, f"Stability violation: μ = {self.mu} ≤ 0"

        # M_*^2 = μ (effective mass squared)
        M_star_squared = self.mu
        assert M_star_squared > 0, f"Stability violation: M_*^2 = {M_star_squared} ≤ 0"

    def compute_effective_metric(self) -> np.ndarray:
        """
        Compute effective metric from VBP envelope.

        Physical Meaning:
            Computes the effective metric g_eff[Θ] from the
            VBP envelope dynamics. This metric describes the
            geometry of the VBP envelope and replaces the
            classical spacetime metric in 7D BVP theory.

        Returns:
            Effective metric tensor g_eff[Θ]
        """
        # Get phase field from system
        phase_field = self._get_phase_field_from_system()

        # Solve phase envelope balance equation
        envelope_result = self.envelope_solver.solve_phase_envelope_balance(phase_field)

        return envelope_result["effective_metric"]

    def _get_phase_field_from_system(self) -> np.ndarray:
        """
        Get phase field from system.

        Physical Meaning:
            Extracts the phase field configuration from the
            system for gravitational calculations.
        """
        if hasattr(self.system, "phase_field"):
            return self.system.phase_field
        else:
            return self._create_default_phase_field()

    def _create_default_phase_field(self) -> np.ndarray:
        """
        Create default phase field for testing.

        Physical Meaning:
            Creates a simple phase field configuration for
            gravitational calculations when no field is available.
        """
        N = self.gravity_params.get("resolution", 256)
        field = np.ones((N, N, N), dtype=complex)
        return field

    def analyze_envelope_curvature(self) -> Dict[str, Any]:
        """
        Analyze VBP envelope curvature.

        Physical Meaning:
            Computes and analyzes all aspects of VBP envelope
            curvature including envelope curvature descriptors,
            anisotropy measures, and focusing rates.

        Returns:
            Dictionary containing envelope curvature analysis
        """
        # Get phase field from system
        phase_field = self._get_phase_field_from_system()

        # Compute envelope curvature descriptors
        curvature_descriptors = self.curvature_calc.compute_envelope_curvature(
            phase_field
        )

        # Compute envelope invariants
        invariants = self.curvature_calc.compute_envelope_invariants(phase_field)

        return {
            "envelope_curvature_scalar": curvature_descriptors[
                "envelope_curvature_scalar"
            ],
            "anisotropy_index": curvature_descriptors["anisotropy_index"],
            "focusing_rate": curvature_descriptors["focusing_rate"],
            "effective_metric": curvature_descriptors["effective_metric"],
            "curvature_invariants": invariants,
        }

    def compute_gravitational_waves(self) -> Dict[str, Any]:
        """
        Compute gravitational waves from VBP envelope dynamics.

        Physical Meaning:
            Calculates gravitational waves generated by the
            VBP envelope dynamics. Waves propagate at c_T=c_φ
            and follow GW-1 amplitude law.

        Returns:
            Dictionary containing gravitational wave properties
        """
        # Get phase field from system
        phase_field = self._get_phase_field_from_system()

        # Solve phase envelope balance equation
        envelope_result = self.envelope_solver.solve_phase_envelope_balance(phase_field)

        # Compute gravitational waves from envelope solution
        waves = self.waves_calc.compute_gravitational_waves(
            envelope_result["envelope_solution"]
        )

        return waves

    def compute_envelope_effects(self) -> Dict[str, Any]:
        """
        Compute all VBP envelope gravitational effects.

        Physical Meaning:
            Calculates all gravitational effects from VBP envelope
            dynamics including envelope curvature, gravitational waves,
            and effective metric.

        Returns:
            Dictionary containing all envelope gravitational effects
        """
        # Get phase field
        phase_field = self._get_phase_field_from_system()

        # Solve phase envelope balance equation
        envelope_result = self.envelope_solver.solve_phase_envelope_balance(phase_field)

        # Compute all envelope gravitational effects
        curvature_analysis = self.analyze_envelope_curvature()
        gravitational_waves = self.compute_gravitational_waves()

        return {
            "envelope_curvature": curvature_analysis,
            "gravitational_waves": gravitational_waves,
            "envelope_solution": envelope_result["envelope_solution"],
            "effective_metric": envelope_result["effective_metric"],
            "curvature_descriptors": envelope_result["curvature_descriptors"],
        }
