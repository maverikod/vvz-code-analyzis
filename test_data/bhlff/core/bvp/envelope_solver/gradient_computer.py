"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Gradient computation for 7D BVP envelope equation.

This module implements gradient computation for fallback gradient descent
when Newton-Raphson method fails in solving the 7D BVP envelope equation.

Physical Meaning:
    Computes the gradient of the residual norm for use in gradient descent
    when Newton method fails, providing robust fallback optimization.

Mathematical Foundation:
    Gradient is ∇||r||² = 2 * Re(r* * ∂r/∂a) computed using finite differences.

Example:
    >>> computer = GradientComputer(domain, constants)
    >>> gradient = computer.compute_gradient(envelope, source)
"""

import numpy as np
from typing import Dict, Any

from ...domain import Domain
from ..bvp_constants import BVPConstants
from ..abstract_solver_core import AbstractSolverCore


class GradientComputer:
    """
    Gradient computation for 7D BVP envelope equation.

    Physical Meaning:
        Computes the gradient of the residual norm for use in gradient descent
        when Newton method fails, providing robust fallback optimization.

    Mathematical Foundation:
        Gradient is ∇||r||² = 2 * Re(r* * ∂r/∂a) computed using finite differences.

    Attributes:
        domain (Domain): 7D computational domain.
        constants (BVPConstants): BVP constants instance.
        residual_computer (ResidualComputer): Residual computation component.
    """

    def __init__(self, domain: Domain, constants: BVPConstants) -> None:
        """
        Initialize gradient computer.

        Physical Meaning:
            Sets up the gradient computation with parameters
            for the nonlinear envelope equation.

        Args:
            domain (Domain): Computational domain.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.constants = constants
        self.residual_computer = AbstractSolverCore(domain, {})

    def compute_gradient(self, envelope: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute gradient for fallback gradient descent.

        Physical Meaning:
            Computes the gradient of the residual norm for use
            in gradient descent when Newton method fails.

        Mathematical Foundation:
            Gradient is ∇||r||² = 2 * Re(r* * ∂r/∂a).

        Args:
            envelope (np.ndarray): Current envelope estimate.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Gradient vector.
        """
        # Compute residual
        residual = self.residual_computer.compute_residual(envelope, source)

        # Compute gradient using finite differences
        gradient = np.zeros_like(envelope)
        h = self.constants.get_numerical_parameter("finite_diff_step")

        for i in range(envelope.size):
            # Create perturbation
            envelope_pert = envelope.flatten().copy()
            envelope_pert[i] += h
            envelope_pert = envelope_pert.reshape(envelope.shape)

            # Compute perturbed residual
            pert_residual = self.residual_computer.compute_residual(
                envelope_pert, source
            )

            # Compute gradient component
            gradient.flat[i] = np.sum((pert_residual - residual).conj() * residual) / h

        return gradient

    def __repr__(self) -> str:
        """String representation of gradient computer."""
        return f"GradientComputer(domain={self.domain})"
