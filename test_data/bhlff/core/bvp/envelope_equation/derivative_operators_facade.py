"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for derivative operators in 7D BVP envelope equation.

This module provides a unified interface to all derivative operators
needed for the 7D BVP envelope equation, coordinating spatial, phase,
and temporal operators through a single facade class.

Physical Meaning:
    The derivative operators facade provides a unified interface to
    all derivative operations needed for the 7D envelope equation
    in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, coordinating spatial,
    phase, and temporal derivatives.

Mathematical Foundation:
    Coordinates finite difference operators for spatial coordinates,
    periodic operators for phase coordinates, and backward difference
    operators for temporal evolution through a single interface.

Example:
    >>> operators = DerivativeOperators7D(domain_7d)
    >>> operators.setup_operators()
    >>> gradient = operators.apply_spatial_gradient(field, axis=0)
"""

import numpy as np
from typing import Tuple

from ...domain.domain_7d import Domain7D
from .derivative_operators.spatial_operators import SpatialOperators
from .derivative_operators.phase_operators import PhaseOperators
from .derivative_operators.temporal_operators import TemporalOperators


class DerivativeOperators7D:
    """
    7D derivative operators facade for BVP envelope equation.

    Physical Meaning:
        Provides a unified interface to all derivative operators needed
        for the 7D envelope equation, including spatial gradients/divergences,
        phase gradients/divergences, and temporal derivatives with appropriate
        boundary conditions.

    Mathematical Foundation:
        Coordinates finite difference operators for spatial coordinates,
        periodic operators for phase coordinates, and backward difference
        operators for temporal evolution.
    """

    def __init__(self, domain_7d: Domain7D):
        """
        Initialize derivative operators facade.

        Physical Meaning:
            Sets up the derivative operators facade with the 7D computational
            domain, initializing all component operators for spatial, phase,
            and temporal derivatives.

        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d

        # Initialize component operators
        self.spatial_operators = SpatialOperators(domain_7d)
        self.phase_operators = PhaseOperators(domain_7d)
        self.temporal_operators = TemporalOperators(domain_7d)

    def setup_operators(self) -> None:
        """
        Setup all derivative operators for 7D space-time.

        Physical Meaning:
            Initializes all derivative operators including spatial,
            phase, and temporal operators with appropriate boundary
            conditions for the 7D envelope equation.
        """
        # Setup all component operators
        self.spatial_operators.setup_operators()
        self.phase_operators.setup_operators()
        self.temporal_operators.setup_operators()

    # Spatial operator methods
    def apply_spatial_gradient(self, field: np.ndarray, axis: int) -> np.ndarray:
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
        return self.spatial_operators.apply_gradient(field, axis)

    def apply_spatial_divergence(self, field: np.ndarray, axis: int) -> np.ndarray:
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
        return self.spatial_operators.apply_divergence(field, axis)

    # Phase operator methods
    def apply_phase_gradient(self, field: np.ndarray, axis: int) -> np.ndarray:
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
        return self.phase_operators.apply_gradient(field, axis)

    def apply_phase_divergence(self, field: np.ndarray, axis: int) -> np.ndarray:
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
        return self.phase_operators.apply_divergence(field, axis)

    # Temporal operator methods
    def apply_temporal_derivative(self, field: np.ndarray) -> np.ndarray:
        """
        Apply temporal derivative operator.

        Physical Meaning:
            Applies the temporal derivative operator to compute the
            time derivative of the field using backward differences.

        Args:
            field: Field to differentiate in time.

        Returns:
            np.ndarray: Temporal derivative of the field.
        """
        return self.temporal_operators.apply_derivative(field)

    # Access to component operators for advanced usage
    @property
    def spatial(self) -> SpatialOperators:
        """Get spatial operators component."""
        return self.spatial_operators

    @property
    def phase(self) -> PhaseOperators:
        """Get phase operators component."""
        return self.phase_operators

    @property
    def temporal(self) -> TemporalOperators:
        """Get temporal operators component."""
        return self.temporal_operators
