"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Solving methods for phase envelope balance solver.

This module provides solving methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class PhaseEnvelopeBalanceSolverSolveMixin:
    """Mixin providing solving methods."""
    
    def solve_phase_envelope_balance(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Solve phase envelope balance equation for VBP envelope dynamics.
        
        Physical Meaning:
            Solves the phase envelope balance equation D[Θ] = source where
            the balance operator D includes time memory (Γ,K) and spatial
            (−Δ)^β terms with c_φ(a,k), χ/κ bridge.
        """
        # Build balance operator D
        balance_operator = self._build_balance_operator(phase_field)

        # Solve envelope balance equation
        envelope_solution = self._solve_envelope_balance(balance_operator, phase_field)

        # Compute effective metric and curvature
        g_eff = self._compute_effective_metric_from_solution(envelope_solution)
        curvature_descriptors = self.curvature_calc.compute_envelope_curvature(
            envelope_solution
        )

        return {
            "envelope_solution": envelope_solution,
            "effective_metric": g_eff,
            "curvature_descriptors": curvature_descriptors,
            "balance_operator": balance_operator,
        }
    
    def _solve_envelope_balance(
        self, balance_operator: Dict[str, Any], phase_field: np.ndarray
    ) -> np.ndarray:
        """
        Solve envelope balance equation.
        
        Physical Meaning:
            Solves the envelope balance equation D[Θ] = source using
            the constructed balance operator and phase field configuration.
        """
        # Initialize solution
        solution = phase_field.copy()

        # Iterative solution
        for iteration in range(self.max_iterations):
            # Apply balance operator
            residual = self._apply_balance_operator(balance_operator, solution)

            # Check convergence
            if np.max(np.abs(residual)) < self.tolerance:
                break

            # Update solution
            solution += 0.01 * residual

        return solution
    
    def _apply_balance_operator(
        self, balance_operator: Dict[str, Any], solution: np.ndarray
    ) -> np.ndarray:
        """
        Apply balance operator to solution.
        
        Physical Meaning:
            Applies the balance operator D[Θ] to the current solution
            to compute the residual for the envelope balance equation.
        """
        # Full application of balance operator with FFT operations
        # Transform solution to spectral space for efficient computation
        solution_spectral = np.fft.fftn(solution)

        # Apply spatial fractional Laplacian operator in spectral space
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)

        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)

        # Spatial operator: μ(-Δ)^β in spectral space
        spatial_operator = self.mu * (k_magnitude ** (2 * self.beta))
        spatial_residual_spectral = spatial_operator * solution_spectral

        # Apply memory kernel convolution in spectral space
        memory_kernels = self._construct_memory_kernels(solution)
        gamma_spectral = np.fft.fftn(memory_kernels["gamma"])
        k_spectral = np.fft.fftn(memory_kernels["k"])

        # Memory response: Γ * solution
        memory_residual_spectral = gamma_spectral * solution_spectral

        # Bridge terms: K * solution (memory decay)
        bridge_residual_spectral = k_spectral * solution_spectral

        # Total residual in spectral space
        total_residual_spectral = (
            spatial_residual_spectral
            + memory_residual_spectral
            + bridge_residual_spectral
        )

        # Transform back to real space
        total_residual = np.fft.ifftn(total_residual_spectral).real

        return total_residual
    
    def _compute_effective_metric_from_solution(
        self, solution: np.ndarray
    ) -> np.ndarray:
        """
        Compute effective metric from envelope solution.
        
        Physical Meaning:
            Computes the effective metric g_eff[Θ] from the envelope solution.
            This metric describes the geometry of the VBP envelope and replaces
            the classical spacetime metric in 7D BVP theory.
        """
        # Initialize 7D effective metric
        g_eff = np.zeros((7, 7))

        # Time component: g00 = -1/c_φ^2
        g_eff[0, 0] = -1.0 / (self.c_phi**2)

        # Spatial components: gij = A^{ij} = χ'/κ δ^{ij} (isotropic)
        for i in range(1, 4):
            g_eff[i, i] = self.chi_kappa

        # Phase components: gαβ (phase space metric)
        for alpha in range(4, 7):
            g_eff[alpha, alpha] = 1.0  # Unit phase space metric

        # Add solution-dependent corrections
        solution_amplitude = np.mean(np.abs(solution))
        correction_factor = 1.0 + 0.1 * solution_amplitude

        for i in range(7):
            g_eff[i, i] *= correction_factor

        return g_eff

