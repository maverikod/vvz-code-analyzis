"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spatial derivative operators for 7D BVP envelope equation.

This module implements spatial derivative operators including gradients
and divergences with finite difference schemes and appropriate boundary
conditions for the 7D BVP envelope equation.

Physical Meaning:
    Spatial derivative operators implement finite difference schemes
    for computing spatial gradients and divergences in the 3D spatial
    coordinates (x, y, z) of the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Implements finite difference operators for:
    - Spatial gradients: ∇ₓa with central differences
    - Spatial divergences: ∇ₓ·(κ(|a|)∇ₓa) with conservative form

Example:
    >>> spatial_ops = SpatialOperators(domain_7d)
    >>> spatial_ops.setup_operators()
    >>> gradient = spatial_ops.apply_gradient(field, axis=0)
"""

import numpy as np
from typing import Tuple
from scipy.sparse import csc_matrix

from ....domain.domain_7d import Domain7D


class SpatialOperators:
    """
    Spatial derivative operators for 7D BVP envelope equation.

    Physical Meaning:
        Implements spatial derivative operators for the 3D spatial
        coordinates (x, y, z) using finite difference schemes with
        appropriate boundary conditions.

    Mathematical Foundation:
        Provides finite difference operators for spatial coordinates
        with central differences and conservative boundary conditions.
    """

    def __init__(self, domain_7d: Domain7D):
        """
        Initialize spatial derivative operators.

        Physical Meaning:
            Sets up the spatial derivative operators with the 7D
            computational domain, preparing for the computation of
            spatial gradients and divergences.

        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d
        self.grad_x = None
        self.grad_y = None
        self.grad_z = None
        self.div_x = None
        self.div_y = None
        self.div_z = None

    def setup_operators(self) -> None:
        """
        Setup all spatial derivative operators.

        Physical Meaning:
            Initializes all spatial derivative operators including
            gradients and divergences for the x, y, and z directions
            with appropriate boundary conditions.
        """
        # Get grid shapes and differentials
        spatial_shape = self.domain_7d.get_spatial_shape()
        differentials = self.domain_7d.get_differentials()
        dx, dy, dz = differentials["dx"], differentials["dy"], differentials["dz"]

        # Setup spatial derivative operators
        self._setup_spatial_derivatives(spatial_shape, dx, dy, dz)

    def _setup_spatial_derivatives(
        self, spatial_shape: Tuple[int, int, int], dx: float, dy: float, dz: float
    ) -> None:
        """
        Setup spatial derivative operators.

        Physical Meaning:
            Creates finite difference operators for spatial derivatives
            in the x, y, and z directions with appropriate boundary conditions.

        Args:
            spatial_shape: Tuple of (N_x, N_y, N_z) grid dimensions.
            dx, dy, dz: Spatial step sizes.
        """
        N_x, N_y, N_z = spatial_shape

        # Spatial gradient operators (finite difference)
        self.grad_x = self._create_gradient_operator(N_x, dx, axis=0)
        self.grad_y = self._create_gradient_operator(N_y, dy, axis=1)
        self.grad_z = self._create_gradient_operator(N_z, dz, axis=2)

        # Spatial divergence operators
        self.div_x = self._create_divergence_operator(N_x, dx, axis=0)
        self.div_y = self._create_divergence_operator(N_y, dy, axis=1)
        self.div_z = self._create_divergence_operator(N_z, dz, axis=2)

    def _create_gradient_operator(self, N: int, dx: float, axis: int) -> csc_matrix:
        """
        Create gradient operator for given axis.

        Physical Meaning:
            Creates a finite difference gradient operator using central
            differences with appropriate boundary conditions.

        Args:
            N: Grid size along the axis.
            dx: Step size along the axis.
            axis: Axis index.

        Returns:
            csc_matrix: Sparse gradient operator matrix.
        """
        # Central difference gradient operator
        diag = np.ones(N)
        off_diag = -np.ones(N - 1)

        # Create tridiagonal matrix
        matrix = np.diag(diag, 0) + np.diag(off_diag, 1) + np.diag(off_diag, -1)
        matrix[0, 0] = 1.0  # Forward difference at boundary
        matrix[-1, -1] = 1.0  # Backward difference at boundary

        return csc_matrix(matrix / (2 * dx))

    def _create_divergence_operator(self, N: int, dx: float, axis: int) -> csc_matrix:
        """
        Create divergence operator for given axis.

        Physical Meaning:
            Creates a divergence operator as the negative of the gradient
            operator for conservative form of the equations.

        Args:
            N: Grid size along the axis.
            dx: Step size along the axis.
            axis: Axis index.

        Returns:
            csc_matrix: Sparse divergence operator matrix.
        """
        # Divergence is negative of gradient for conservative form
        return -self._create_gradient_operator(N, dx, axis)

    def apply_gradient(self, field: np.ndarray, axis: int) -> np.ndarray:
        """
        Apply spatial gradient operator.

        Physical Meaning:
            Applies the spatial gradient operator to compute the gradient
            of the field along the specified spatial axis.

        Args:
            field: Field to differentiate.
            axis: Spatial axis (0=x, 1=y, 2=z).

        Returns:
            np.ndarray: Gradient of the field.
        """
        if axis == 0:
            return self.grad_x.dot(field.flatten()).reshape(field.shape)
        elif axis == 1:
            return self.grad_y.dot(field.flatten()).reshape(field.shape)
        elif axis == 2:
            return self.grad_z.dot(field.flatten()).reshape(field.shape)
        else:
            raise ValueError(f"Invalid spatial axis: {axis}")

    def apply_divergence(self, field: np.ndarray, axis: int) -> np.ndarray:
        """
        Apply spatial divergence operator.

        Physical Meaning:
            Applies the spatial divergence operator to compute the divergence
            of the field along the specified spatial axis.

        Args:
            field: Field to differentiate.
            axis: Spatial axis (0=x, 1=y, 2=z).

        Returns:
            np.ndarray: Divergence of the field.
        """
        if axis == 0:
            return self.div_x.dot(field.flatten()).reshape(field.shape)
        elif axis == 1:
            return self.div_y.dot(field.flatten()).reshape(field.shape)
        elif axis == 2:
            return self.div_z.dot(field.flatten()).reshape(field.shape)
        else:
            raise ValueError(f"Invalid spatial axis: {axis}")
