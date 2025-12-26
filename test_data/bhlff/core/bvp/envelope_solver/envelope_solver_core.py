"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core envelope solver facade for BVP envelope equation.

This module provides the main facade class for the envelope solver,
coordinating all components for solving the 7D BVP envelope equation.

Physical Meaning:
    Provides the main interface for solving the nonlinear 7D envelope
    equation ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) using advanced
    numerical methods in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Coordinates Newton-Raphson method with line search and regularization
    for robust solution of nonlinear 7D envelope equations.

Example:
    >>> core = EnvelopeSolverCore(domain, config)
    >>> residual = core.compute_residual(envelope, source)
    >>> jacobian = core.compute_jacobian(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain import Domain
from ..bvp_constants import BVPConstants
from ..abstract_solver_core import AbstractSolverCore
from .gradient_computer import GradientComputer


class EnvelopeSolverCore(AbstractSolverCore):
    """
    Core facade for 7D BVP envelope equation solver.

    Physical Meaning:
        Coordinates all components for solving the nonlinear 7D envelope
        equation using advanced numerical methods in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        Provides unified interface for Newton-Raphson method with line search
        and regularization for robust solution of nonlinear 7D envelope equations.

    Attributes:
        domain (Domain): 7D computational domain.
        constants (BVPConstants): BVP constants instance.
        gradient_computer (GradientComputer): Gradient computation component.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ) -> None:
        """
        Initialize envelope solver core.

        Physical Meaning:
            Sets up the core mathematical operations with parameters
            for the nonlinear envelope equation.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Configuration parameters.
            constants (BVPConstants, optional): BVP constants instance.
        """
        super().__init__(domain, config)
        self.constants = constants or BVPConstants(config)

        # Initialize only the components that are still used
        self.gradient_computer = GradientComputer(domain, self.constants)

    # compute_residual method removed - now inherits from AbstractSolverCore

    # compute_jacobian method removed - now inherits from AbstractSolverCore

    # solve_linear_system method removed - now inherits from AbstractSolverCore

    def solve_newton_system(
        self, jacobian: np.ndarray, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve Newton-Raphson system for envelope equation.

        Physical Meaning:
            Solves the linearized Newton-Raphson system J·δa = -R
            for the envelope equation update δa.

        Mathematical Foundation:
            Solves J·δa = -R where J is the Jacobian matrix and R is the residual.
            Uses the inherited solve_linear_system method for the actual solving.

        Args:
            jacobian (np.ndarray): Jacobian matrix J.
            residual (np.ndarray): Residual vector R.

        Returns:
            np.ndarray: Solution update δa.
        """
        return self.solve_linear_system(jacobian, -residual)

    def compute_gradient(self, envelope: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute gradient for fallback gradient descent.

        Physical Meaning:
            Computes the gradient of the residual norm for use
            in gradient descent when Newton method fails.

        Args:
            envelope (np.ndarray): Current envelope estimate.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Gradient vector.
        """
        return self.gradient_computer.compute_gradient(envelope, source)

    def __repr__(self) -> str:
        """String representation of envelope solver core."""
        return (
            f"EnvelopeSolverCore(domain={self.domain.shape}, "
            f"constants={self.constants})"
        )
