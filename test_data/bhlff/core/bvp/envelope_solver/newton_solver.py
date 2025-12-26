"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Newton-Raphson solver for 7D BVP envelope equation.

This module implements the Newton-Raphson system solver for the 7D BVP
envelope equation with regularization and advanced numerical methods.

Physical Meaning:
    Solves the linear system J * δa = -r for the Newton update step
    using advanced numerical methods with regularization.

Mathematical Foundation:
    Solves J * δa = -r where J is the Jacobian and r is the residual,
    with regularization for numerical stability.

Example:
    >>> solver = NewtonSolver(domain, constants)
    >>> delta = solver.solve_newton_system(jacobian, residual)
"""

import numpy as np
from typing import Dict, Any

from ...domain import Domain
from ..bvp_constants import BVPConstants


class NewtonSolver:
    """
    Newton-Raphson solver for 7D BVP envelope equation.

    Physical Meaning:
        Solves the linear system J * δa = -r for the Newton update step
        using advanced numerical methods with regularization.

    Mathematical Foundation:
        Solves J * δa = -r where J is the Jacobian and r is the residual,
        with regularization for numerical stability.

    Attributes:
        domain (Domain): 7D computational domain.
        constants (BVPConstants): BVP constants instance.
    """

    def __init__(self, domain: Domain, constants: BVPConstants) -> None:
        """
        Initialize Newton solver.

        Physical Meaning:
            Sets up the Newton-Raphson solver with parameters
            for the nonlinear envelope equation.

        Args:
            domain (Domain): Computational domain.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.constants = constants

    def solve_newton_system(
        self, jacobian: np.ndarray, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve Newton system J * δa = -r.

        Physical Meaning:
            Solves the linear system for the Newton update step
            using advanced numerical methods.

        Mathematical Foundation:
            Solves J * δa = -r where J is the Jacobian and r is the residual.

        Args:
            jacobian (np.ndarray): Jacobian matrix J.
            residual (np.ndarray): Residual vector r.

        Returns:
            np.ndarray: Newton update step δa.
        """
        # Use advanced linear solver with regularization
        # Add regularization for numerical stability
        regularization_value = self.constants.get_numerical_parameter("regularization")
        regularization = regularization_value * np.eye(jacobian.shape[0])
        jacobian_reg = jacobian + regularization

        # Solve using least squares for robustness
        delta_envelope, _, _, _ = np.linalg.lstsq(
            jacobian_reg, -residual.flatten(), rcond=None
        )

        return delta_envelope.reshape(residual.shape)

    def __repr__(self) -> str:
        """String representation of Newton solver."""
        return f"NewtonSolver(domain={self.domain})"
