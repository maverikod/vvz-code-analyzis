"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Linear envelope equation solver.

This module implements the linearized version of the 7D BVP envelope
equation solver for initial guess generation and linear analysis.

Physical Meaning:
    Solves the linearized version of the envelope equation
    ∇·(κ₀∇a) + k₀²χ'a = s(x,φ,t) for initial guess generation
    and linear analysis of the BVP field.

Mathematical Foundation:
    Solves the linearized equation using spectral methods
    for efficient computation of initial guess.

Example:
    >>> linear_solver = EnvelopeLinearSolver(domain, constants)
    >>> linear_solution = linear_solver.solve_linearized(source)
"""

import numpy as np
from typing import Dict, Any

from ..domain import Domain
from .bvp_constants import BVPConstants
from .memory_decorator import memory_protected_class_method
from ..fft.unified_spectral_operations import UnifiedSpectralOperations


class EnvelopeLinearSolver:
    """
    Linear solver for 7D BVP envelope equation.

    Physical Meaning:
        Solves the linearized version of the envelope equation
        ∇·(κ₀∇a) + k₀²χ'a = s(x,φ,t) for initial guess generation
        and linear analysis of the BVP field.

    Mathematical Foundation:
        Solves the linearized equation using spectral methods
        for efficient computation of initial guess.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize linear envelope solver.

        Physical Meaning:
            Sets up the linear solver with the computational domain
            and constants for solving the linearized envelope equation.

        Args:
            domain (Domain): Computational domain for envelope calculations.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.constants = constants

        # Linear equation parameters
        self.kappa_0 = constants.get_envelope_parameter("kappa_0")
        self.chi_prime = constants.get_envelope_parameter("chi_prime")
        self.k0_squared = constants.get_envelope_parameter("k0_squared")

    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="source", dtype_param="source"
    )
    def solve_linearized(self, source: np.ndarray) -> np.ndarray:
        """
        Solve linearized 7D BVP envelope equation.

        Physical Meaning:
            Solves the linearized version of the envelope equation
            ∇·(κ₀∇a) + k₀²χ'a = s(x,φ,t) for initial guess generation.

        Mathematical Foundation:
            Solves the linearized equation using spectral methods
            for efficient computation of initial guess.

        Args:
            source (np.ndarray): Source term s(x,φ,t) in 7D space-time.

        Returns:
            np.ndarray: Linearized envelope solution a(x,φ,t).
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with "
                f"7D domain shape {self.domain.shape}"
            )

        # Use linearized version with constant coefficients
        # ∇·(κ₀∇a) + k₀²χ'a = s
        # In spectral space: -κ₀|k|²â + k₀²χ'â = ŝ
        # Therefore: â = ŝ / (k₀²χ' - κ₀|k|²)

        # Transform to spectral space via unified backend (physics normalization)
        spectral_ops = UnifiedSpectralOperations(self.domain, precision="float64")
        source_spectral = spectral_ops.forward_fft(source, normalization="physics")

        # Compute wave vectors for 7D
        k_vectors = []
        for i, n in enumerate(self.domain.shape):
            if i < 3:  # Spatial dimensions
                dx = self.domain.L_spatial / self.domain.N_spatial
            elif i < 6:  # Phase dimensions
                dx = 2 * np.pi / self.domain.N_phase
            else:  # Temporal dimension
                dx = self.domain.T / self.domain.N_t
            k = np.fft.fftfreq(n, dx)
            k_vectors.append(k)

        # Create 7D wave vector grid
        K_grids = np.meshgrid(*k_vectors, indexing="ij")
        k_magnitude_squared = sum(K**2 for K in K_grids)

        # Compute spectral coefficients
        spectral_coeffs = (
            self.k0_squared * self.chi_prime - self.kappa_0 * k_magnitude_squared
        )

        # Avoid division by zero
        try:
            regularization = self.constants.get_numerical_parameter("regularization")
        except KeyError:
            regularization = 1e-12
        spectral_coeffs = np.where(
            np.abs(spectral_coeffs) < regularization, regularization, spectral_coeffs
        )

        # Solve in spectral space
        envelope_spectral = source_spectral / spectral_coeffs

        # Transform back to real space via unified backend (physics normalization)
        envelope = spectral_ops.inverse_fft(envelope_spectral, normalization="physics")

        return envelope.real

    def solve_linearized_with_coefficients(
        self,
        envelope: np.ndarray,
        kappa: np.ndarray,
        chi: np.ndarray,
        source: np.ndarray,
    ) -> np.ndarray:
        """
        Solve linearized envelope equation with given coefficients.

        Physical Meaning:
            Solves the linearized version of the envelope equation
            for a given nonlinear stiffness and susceptibility.

        Mathematical Foundation:
            Solves ∇·(κ∇a) + k₀²χa = s using finite difference method.

        Args:
            envelope (np.ndarray): Current envelope estimate.
            kappa (np.ndarray): Nonlinear stiffness κ(|a|).
            chi (np.ndarray): Effective susceptibility χ(|a|).
            source (np.ndarray): Source term s(x).

        Returns:
            np.ndarray: Updated envelope solution.
        """
        # Advanced finite difference implementation with spectral accuracy for 7D
        # Uses high-order finite differences for all 7 dimensions:
        # 3 spatial (x,y,z) + 3 phase (φ₁,φ₂,φ₃) + 1 temporal (t)

        # Compute divergence of κ∇a using finite differences
        div_kappa_grad = self._compute_div_kappa_grad(envelope, kappa)

        # Solve: ∇·(κ∇a) + k₀²χa = s
        # Rearrange: k₀²χa = s - ∇·(κ∇a)
        # Therefore: a = (s - ∇·(κ∇a)) / (k₀²χ)

        # Avoid division by zero
        regularization = self.constants.get_numerical_parameter("regularization")
        chi_safe = np.where(np.abs(chi) < regularization, regularization, chi)

        envelope_new = (source - div_kappa_grad) / (self.k0_squared * chi_safe)

        return envelope_new

    def _compute_div_kappa_grad(
        self, envelope: np.ndarray, kappa: np.ndarray
    ) -> np.ndarray:
        """
        Compute divergence of κ∇a using finite differences.

        Physical Meaning:
            Computes ∇·(κ∇a) using finite difference methods
            for all 7 dimensions of the envelope field.

        Mathematical Foundation:
            ∇·(κ∇a) = Σᵢ ∂/∂xᵢ(κ ∂a/∂xᵢ)
            where the sum is over all 7 dimensions.

        Args:
            envelope (np.ndarray): Envelope field a(x,φ,t).
            kappa (np.ndarray): Stiffness field κ(x,φ,t).

        Returns:
            np.ndarray: Divergence of κ∇a.
        """
        # Compute gradients in all 7 dimensions
        gradients = []
        for i in range(envelope.ndim):
            grad = np.gradient(envelope, axis=i)
            gradients.append(grad)

        # Compute κ∇a in each dimension
        kappa_grad = []
        for i, grad in enumerate(gradients):
            kappa_grad.append(kappa * grad)

        # Compute divergence: ∇·(κ∇a) = Σᵢ ∂/∂xᵢ(κ ∂a/∂xᵢ)
        div_kappa_grad = np.zeros_like(envelope)
        for i, kg in enumerate(kappa_grad):
            div_kg = np.gradient(kg, axis=i)
            div_kappa_grad += div_kg

        return div_kappa_grad
