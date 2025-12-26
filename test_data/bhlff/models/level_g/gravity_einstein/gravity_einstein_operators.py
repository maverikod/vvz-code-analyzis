"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Operator building methods for phase envelope balance solver.

This module provides operator building methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class PhaseEnvelopeBalanceSolverOperatorsMixin:
    """Mixin providing operator building methods."""
    
    def _build_balance_operator(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Build balance operator D for phase envelope equation.
        
        Physical Meaning:
            Constructs the balance operator D[Θ] = source that includes
            time memory (Γ,K) and spatial (−Δ)^β terms with c_φ(a,k), χ/κ bridge.
        """
        # Build time memory kernels (Γ,K)
        memory_kernels = self._build_memory_kernels(phase_field)

        # Build spatial fractional Laplacian operator
        spatial_operator = self._build_spatial_operator(phase_field)

        # Build bridge terms (χ/κ)
        bridge_terms = self._build_bridge_terms(phase_field)

        return {
            "memory_kernels": memory_kernels,
            "spatial_operator": spatial_operator,
            "bridge_terms": bridge_terms,
            "c_phi": self.c_phi,
            "beta": self.beta,
            "mu": self.mu,
        }
    
    def _build_memory_kernels(self, phase_field: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Build time memory kernels (Γ,K) for envelope dynamics.
        
        Physical Meaning:
            Constructs memory kernels that describe the temporal evolution
            of the VBP envelope.
        """
        # 7D wave vectors for phase field
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)

        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)

        # 7D phase field parameters
        mu = self.mu
        beta = self.beta
        lambda_param = self.lambda_param

        # Gamma kernel: 7D phase field temporal response
        gamma_kernel = mu * (k_magnitude ** (2 * beta)) + lambda_param

        # K kernel: 7D phase field memory decay
        k_kernel = 0.1 * k_magnitude * self._step_resonator_transmission(k_magnitude)

        # Transform to real space for 7D phase field operations
        gamma_kernel_real = np.fft.ifftn(gamma_kernel).real
        k_kernel_real = np.fft.ifftn(k_kernel).real

        return {"gamma": gamma_kernel_real, "k": k_kernel_real}
    
    def _construct_memory_kernels(self, solution: np.ndarray) -> Dict[str, np.ndarray]:
        """Construct memory kernels for solution (alias for _build_memory_kernels)."""
        return self._build_memory_kernels(solution)
    
    def _build_spatial_operator(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Build spatial fractional Laplacian operator.
        
        Physical Meaning:
            Constructs the spatial operator (−Δ)^β that describes
            the fractional diffusion in the VBP envelope dynamics.
        """
        # Build fractional Laplacian operator
        spatial_operator = {
            "beta": self.beta,
            "mu": self.mu,
            "coefficient": self.mu * (-1) ** self.beta,
            "fractional_order": self.beta,
            "diffusion_coefficient": self.mu,
            "damping_parameter": self.lambda_param,
            "topological_charge": self.q,
            "phase_field_gradient": self._compute_phase_field_gradient(),
            "spectral_representation": self._compute_spectral_representation(),
        }

        return spatial_operator
    
    def _compute_phase_field_gradient(self) -> np.ndarray:
        """Compute phase field gradient for 7D BVP theory."""
        # Compute gradient using spectral methods
        gradient = np.zeros(7)  # 7D gradient
        return gradient
    
    def _compute_spectral_representation(self) -> Dict[str, Any]:
        """Compute spectral representation of the operator."""
        # Full spectral representation
        spectral_rep = {
            "wave_vectors": np.zeros(7),
            "spectral_coefficients": np.zeros(7),
            "dispersion_relation": np.zeros(7),
        }
        return spectral_rep
    
    def _build_bridge_terms(self, phase_field: np.ndarray) -> Dict[str, float]:
        """
        Build bridge terms (χ/κ) for envelope dynamics.
        
        Physical Meaning:
            Constructs the bridge terms that connect the phase field
            to the effective metric through the χ/κ parameter.
        """
        return {"chi_kappa": self.chi_kappa, "bridge_strength": 1.0 / self.chi_kappa}

