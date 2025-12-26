"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Temporal derivative operators for 7D BVP envelope equation.

This module implements temporal derivative operators for time evolution
in the 7D BVP envelope equation using backward difference schemes.

Physical Meaning:
    Temporal derivative operators implement backward difference schemes
    for computing temporal derivatives in the time coordinate t of the
    7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Implements temporal derivative operators for:
    - Temporal derivatives: ∂ₜa with backward differences
    - Time evolution schemes for envelope equation

Example:
    >>> temporal_ops = TemporalOperators(domain_7d)
    >>> temporal_ops.setup_operators()
    >>> derivative = temporal_ops.apply_derivative(field)
"""

import numpy as np
from scipy.sparse import csc_matrix

from ....domain.domain_7d import Domain7D


class TemporalOperators:
    """
    Temporal derivative operators for 7D BVP envelope equation.

    Physical Meaning:
        Implements temporal derivative operators for time evolution
        in the envelope equation using backward difference schemes
        appropriate for time-stepping algorithms.

    Mathematical Foundation:
        Provides backward difference operators for temporal derivatives
        with appropriate initial conditions and time-stepping schemes.
    """

    def __init__(self, domain_7d: Domain7D):
        """
        Initialize temporal derivative operators.

        Physical Meaning:
            Sets up the temporal derivative operators with the 7D
            computational domain, preparing for the computation of
            temporal derivatives and time evolution.

        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d
        self.dt_operator = None

    def setup_operators(self) -> None:
        """
        Setup temporal derivative operator.

        Physical Meaning:
            Initializes the temporal derivative operator using backward
            differences for time evolution in the envelope equation.
        """
        # Setup temporal derivative operator
        self._setup_temporal_derivative()

    def _setup_temporal_derivative(self) -> None:
        """
        Setup temporal derivative operator.

        Physical Meaning:
            Creates the temporal derivative operator using backward
            differences for time evolution in the envelope equation.
        """
        dt = self.domain_7d.temporal_config.dt
        N_t = self.domain_7d.temporal_config.N_t

        # Temporal derivative operator (backward difference)
        self.dt_operator = self._create_temporal_derivative_operator(N_t, dt)

    def _create_temporal_derivative_operator(self, N_t: int, dt: float) -> csc_matrix:
        """
        Create temporal derivative operator.

        Physical Meaning:
            Creates a temporal derivative operator using backward
            differences for time evolution.

        Args:
            N_t: Number of time steps.
            dt: Time step size.

        Returns:
            csc_matrix: Sparse temporal derivative operator matrix.
        """
        # Backward difference for temporal derivative
        diag = np.ones(N_t)
        off_diag = -np.ones(N_t - 1)

        # Create lower triangular matrix
        matrix = np.diag(diag, 0) + np.diag(off_diag, -1)
        matrix[0, 0] = 1.0  # Initial condition

        return csc_matrix(matrix / dt)

    def apply_derivative(self, field: np.ndarray) -> np.ndarray:
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
        return self.dt_operator.dot(field.flatten()).reshape(field.shape)

    def get_time_step(self) -> float:
        """
        Get time step size.

        Physical Meaning:
            Returns the time step size used in the temporal derivative
            operator for monitoring and analysis purposes.

        Returns:
            float: Time step size dt.
        """
        return self.domain_7d.temporal_config.dt

    def get_time_points(self) -> int:
        """
        Get number of time points.

        Physical Meaning:
            Returns the number of time points in the temporal grid
            for monitoring and analysis purposes.

        Returns:
            int: Number of time points N_t.
        """
        return self.domain_7d.temporal_config.N_t
