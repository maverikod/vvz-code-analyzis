"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmology methods for phase envelope balance solver.

This module provides cosmology methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class PhaseEnvelopeBalanceSolverCosmologyMixin:
    """Mixin providing cosmology methods."""
    
    def solve_with_envelope_effective_metric(
        self, source: np.ndarray
    ) -> Dict[str, Any]:
        """
        Solve phase envelope balance equation using integrated EnvelopeEffectiveMetric.
        
        Physical Meaning:
            Solves the phase envelope balance equation D[Θ] = source using
            the integrated EnvelopeEffectiveMetric class for computing
            the effective metric from envelope dynamics.
        """
        # Solve the phase envelope balance equation
        solution = self.solve_phase_envelope_balance(source)

        # Compute effective metric using integrated EnvelopeEffectiveMetric
        g_eff = self.envelope_metric.compute_envelope_curvature_metric(solution)

        # Compute envelope invariants
        envelope_invariants = self.curvature_calc.compute_envelope_invariants(solution)

        return {
            "solution": solution,
            "effective_metric": g_eff,
            "envelope_invariants": envelope_invariants,
            "envelope_curvature": self.curvature_calc.compute_envelope_curvature(
                solution
            ),
        }
    
    def compute_anisotropic_envelope_solution(
        self, source: np.ndarray
    ) -> Dict[str, Any]:
        """
        Solve phase envelope balance equation with anisotropic envelope metric.
        
        Physical Meaning:
            Solves the phase envelope balance equation using an anisotropic
            effective metric computed from envelope dynamics.
        """
        # Solve the phase envelope balance equation
        solution = self.solve_phase_envelope_balance(source)

        # Compute anisotropic effective metric
        g_eff_anisotropic = self.curvature_calc.compute_anisotropic_envelope_metric(
            solution
        )

        # Compute envelope invariants
        envelope_invariants = self.curvature_calc.compute_envelope_invariants(solution)

        return {
            "solution": solution,
            "anisotropic_effective_metric": g_eff_anisotropic,
            "envelope_invariants": envelope_invariants,
            "anisotropy_measure": envelope_invariants.get("anisotropy", 0.0),
        }
    
    def compute_cosmological_envelope_evolution(
        self, source: np.ndarray, t: float
    ) -> Dict[str, Any]:
        """
        Solve phase envelope balance equation with cosmological evolution.
        
        Physical Meaning:
            Solves the phase envelope balance equation including cosmological
            evolution effects using the integrated EnvelopeEffectiveMetric
            for scale factor computation.
        """
        # Solve the phase envelope balance equation
        solution = self.solve_phase_envelope_balance(source)

        # Compute effective metric
        g_eff = self.envelope_metric.compute_envelope_curvature_metric(solution)

        # Compute cosmological scale factor using VBP envelope dynamics
        scale_factor = self.envelope_metric.compute_scale_factor(t)

        # Apply cosmological evolution to solution
        evolved_solution = solution * scale_factor

        return {
            "solution": solution,
            "evolved_solution": evolved_solution,
            "effective_metric": g_eff,
            "scale_factor": scale_factor,
            "cosmological_time": t,
        }

