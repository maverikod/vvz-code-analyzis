"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase derivative operators for 7D BVP envelope equation.

This module implements phase derivative operators including gradients
and divergences with periodic boundary conditions for the toroidal
phase space in the 7D BVP envelope equation.

Physical Meaning:
    Phase derivative operators implement periodic derivative schemes
    for computing phase gradients and divergences in the 3D phase
    coordinates (φ₁, φ₂, φ₃) of the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Implements periodic derivative operators for:
    - Phase gradients: ∇φa with periodic boundary conditions
    - Phase divergences: ∇φ·(κ(|a|)∇φa) with periodic form

Example:
    >>> phase_ops = PhaseOperators(domain_7d)
    >>> phase_ops.setup_operators()
    >>> gradient = phase_ops.apply_gradient(field, axis=3)
"""

import numpy as np
from typing import Tuple
from scipy.sparse import csc_matrix

from ....domain.domain_7d import Domain7D


class PhaseOperators:
    """
    Phase derivative operators for 7D BVP envelope equation.

    Physical Meaning:
        Implements phase derivative operators for the 3D phase
        coordinates (φ₁, φ₂, φ₃) using periodic boundary conditions
        appropriate for the toroidal phase space.

    Mathematical Foundation:
        Provides periodic derivative operators for phase coordinates
        with central differences and periodic boundary conditions.
    """

    def __init__(self, domain_7d: Domain7D):
        """
        Initialize phase derivative operators.

        Physical Meaning:
            Sets up the phase derivative operators with the 7D
            computational domain, preparing for the computation of
            phase gradients and divergences with periodic boundary
            conditions.

        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d
        self.grad_phi_1 = None
        self.grad_phi_2 = None
        self.grad_phi_3 = None
        self.div_phi_1 = None
        self.div_phi_2 = None
        self.div_phi_3 = None

    def setup_operators(self) -> None:
        """
        Setup all phase derivative operators.

        Physical Meaning:
            Initializes all phase derivative operators including
            gradients and divergences for the φ₁, φ₂, and φ₃ directions
            with periodic boundary conditions.
        """
        # Get grid shapes and differentials
        phase_shape = self.domain_7d.get_phase_shape()
        differentials = self.domain_7d.get_differentials()
        dphi_1, dphi_2, dphi_3 = (
            differentials["dphi_1"],
            differentials["dphi_2"],
            differentials["dphi_3"],
        )

        # Setup phase derivative operators
        self._setup_phase_derivatives(phase_shape, dphi_1, dphi_2, dphi_3)

    def _setup_phase_derivatives(
        self,
        phase_shape: Tuple[int, int, int],
        dphi_1: float,
        dphi_2: float,
        dphi_3: float,
    ) -> None:
        """
        Setup phase derivative operators.

        Physical Meaning:
            Creates periodic derivative operators for phase coordinates
            with periodic boundary conditions appropriate for the
            toroidal phase space.

        Args:
            phase_shape: Tuple of (N_phi_1, N_phi_2, N_phi_3) grid dimensions.
            dphi_1, dphi_2, dphi_3: Phase step sizes.
        """
        N_phi_1, N_phi_2, N_phi_3 = phase_shape

        # Phase gradient operators (periodic boundary conditions)
        self.grad_phi_1 = self._create_periodic_gradient_operator(
            N_phi_1, dphi_1, axis=3
        )
        self.grad_phi_2 = self._create_periodic_gradient_operator(
            N_phi_2, dphi_2, axis=4
        )
        self.grad_phi_3 = self._create_periodic_gradient_operator(
            N_phi_3, dphi_3, axis=5
        )

        # Phase divergence operators
        self.div_phi_1 = self._create_periodic_divergence_operator(
            N_phi_1, dphi_1, axis=3
        )
        self.div_phi_2 = self._create_periodic_divergence_operator(
            N_phi_2, dphi_2, axis=4
        )
        self.div_phi_3 = self._create_periodic_divergence_operator(
            N_phi_3, dphi_3, axis=5
        )

    def _create_periodic_gradient_operator(
        self, N: int, dx: float, axis: int
    ) -> csc_matrix:
        """
        Create periodic gradient operator for phase coordinates.

        Physical Meaning:
            Creates a periodic gradient operator using central differences
            with periodic boundary conditions for the toroidal phase space.

        Args:
            N: Grid size along the axis.
            dx: Step size along the axis.
            axis: Axis index.

        Returns:
            csc_matrix: Sparse periodic gradient operator matrix.
        """
        # Central difference with periodic boundary conditions
        diag = np.zeros(N)
        off_diag_pos = np.ones(N - 1)
        off_diag_neg = -np.ones(N - 1)

        # Create periodic matrix
        matrix = np.diag(diag, 0) + np.diag(off_diag_pos, 1) + np.diag(off_diag_neg, -1)
        matrix[0, -1] = -1.0  # Periodic boundary condition
        matrix[-1, 0] = 1.0  # Periodic boundary condition

        return csc_matrix(matrix / (2 * dx))

    def _create_periodic_divergence_operator(
        self, N: int, dx: float, axis: int
    ) -> csc_matrix:
        """
        Create periodic divergence operator for phase coordinates.

        Physical Meaning:
            Creates a periodic divergence operator as the negative of
            the periodic gradient operator.

        Args:
            N: Grid size along the axis.
            dx: Step size along the axis.
            axis: Axis index.

        Returns:
            csc_matrix: Sparse periodic divergence operator matrix.
        """
        return -self._create_periodic_gradient_operator(N, dx, axis)

    def apply_gradient(self, field: np.ndarray, axis: int) -> np.ndarray:
        """
        Apply phase gradient operator.

        Physical Meaning:
            Applies the phase gradient operator to compute the gradient
            of the field along the specified phase axis with periodic
            boundary conditions.

        Args:
            field: Field to differentiate.
            axis: Phase axis (3=phi_1, 4=phi_2, 5=phi_3).

        Returns:
            np.ndarray: Gradient of the field.
        """
        if axis == 3:
            return self.grad_phi_1.dot(field.flatten()).reshape(field.shape)
        elif axis == 4:
            return self.grad_phi_2.dot(field.flatten()).reshape(field.shape)
        elif axis == 5:
            return self.grad_phi_3.dot(field.flatten()).reshape(field.shape)
        else:
            raise ValueError(f"Invalid phase axis: {axis}")

    def apply_divergence(self, field: np.ndarray, axis: int) -> np.ndarray:
        """
        Apply phase divergence operator.

        Physical Meaning:
            Applies the phase divergence operator to compute the divergence
            of the field along the specified phase axis with periodic
            boundary conditions.

        Args:
            field: Field to differentiate.
            axis: Phase axis (3=phi_1, 4=phi_2, 5=phi_3).

        Returns:
            np.ndarray: Divergence of the field.
        """
        if axis == 3:
            return self.div_phi_1.dot(field.flatten()).reshape(field.shape)
        elif axis == 4:
            return self.div_phi_2.dot(field.flatten()).reshape(field.shape)
        elif axis == 5:
            return self.div_phi_3.dot(field.flatten()).reshape(field.shape)
        else:
            raise ValueError(f"Invalid phase axis: {axis}")
