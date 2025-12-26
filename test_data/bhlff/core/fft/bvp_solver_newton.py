"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Newton-Raphson solver for 7D BVP envelope equation.

This module implements the Newton-Raphson iterative solver for the nonlinear
7D BVP envelope equation with adaptive damping and numerical stability.

Physical Meaning:
    Solves the nonlinear BVP equation using Newton-Raphson iteration:
    a^(n+1) = a^(n) - J^(-1) * R(a^(n))
    where R is the residual and J is the Jacobian matrix.

Mathematical Foundation:
    Newton-Raphson iteration with adaptive damping:
    - Computes residual R(a) = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s
    - Computes Jacobian J = ∂R/∂a
    - Solves J * correction = R for correction
    - Updates solution with adaptive damping

Example:
    >>> newton_solver = BVPSolverNewton(core_solver, parameters)
    >>> solution = newton_solver.solve(source_field, initial_guess)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.domain_7d_bvp import Domain7DBVP
    from ..domain.parameters_7d_bvp import Parameters7DBVP
    from .bvp_solver_core import BVPSolverCore


class BVPSolverNewton:
    """
    Newton-Raphson solver for BVP equation.

    Physical Meaning:
        Implements the Newton-Raphson iterative method for solving the
        nonlinear 7D BVP envelope equation with adaptive damping.

    Mathematical Foundation:
        Newton-Raphson iteration: a^(n+1) = a^(n) - J^(-1) * R(a^(n))
        with adaptive damping based on residual improvement.

    Attributes:
        core (BVPSolverCore): Core BVP solver functionality.
        parameters (Parameters7DBVP): 7D BVP parameters.
        domain (Domain7DBVP): 7D BVP computational domain.
    """

    def __init__(self, core: "BVPSolverCore", parameters: "Parameters7DBVP"):
        """
        Initialize Newton-Raphson solver.

        Physical Meaning:
            Sets up the Newton-Raphson solver with core functionality
            and parameters for iterative solution of the BVP equation.

        Args:
            core (BVPSolverCore): Core BVP solver functionality.
            parameters (Parameters7DBVP): 7D BVP parameters.
        """
        self.core = core
        self.parameters = parameters
        self.domain = core.domain
        self.logger = logging.getLogger(__name__)

        self.logger.info("BVPSolverNewton initialized.")

    def solve(
        self, source_field: np.ndarray, initial_guess: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Solve full nonlinear equation using Newton-Raphson method.

        Physical Meaning:
            Solves the complete nonlinear BVP equation using Newton-Raphson
            iteration to handle the nonlinear terms κ(|a|) and χ(|a|).

        Mathematical Foundation:
            Newton-Raphson iteration: a^(n+1) = a^(n) - J^(-1) R(a^(n))
            where J is the Jacobian matrix and R is the residual.

        Args:
            source_field (np.ndarray): Source term s(x,φ,t).
            initial_guess (Optional[np.ndarray]): Initial guess for solution.

        Returns:
            np.ndarray: Solution field a(x,φ,t).
        """
        # Use linearized solution as initial guess if not provided
        if initial_guess is None:
            initial_guess = self._solve_linearized(source_field)

        # Newton-Raphson iteration with adaptive damping
        solution = initial_guess.copy()
        max_iterations = self.parameters.max_iterations
        tolerance = self.parameters.tolerance
        damping_factor = self.parameters.damping_factor

        previous_residual_norm = float("inf")

        for iteration in range(max_iterations):
            # Compute residual
            residual = self.core.compute_residual(solution, source_field)
            residual_norm = np.linalg.norm(residual)

            # Check convergence
            if residual_norm < tolerance:
                self.logger.info(
                    f"Newton-Raphson converged in {iteration+1} iterations"
                )
                break

            # Adaptive damping based on residual improvement
            if residual_norm > previous_residual_norm:
                damping_factor *= 0.5  # Reduce damping if residual increases
            else:
                damping_factor = min(
                    damping_factor * 1.1, 0.5
                )  # Increase damping if improving

            # Compute Jacobian and solve linear system
            jacobian = self.core.compute_jacobian(solution)
            correction = self.core.solve_linear_system(jacobian, residual)

            # Update solution with adaptive damping and clipping
            solution = solution - damping_factor * correction

            # Clip solution to prevent numerical instability
            solution = np.clip(solution, -10.0, 10.0)

            previous_residual_norm = residual_norm
            self.logger.debug(
                f"Iteration {iteration+1}: residual_norm = {residual_norm:.2e}, damping = {damping_factor:.3f}"
            )

        else:
            self.logger.warning(
                f"Newton-Raphson did not converge in {max_iterations} iterations"
            )

        return solution

    def _solve_linearized(self, source_field: np.ndarray) -> np.ndarray:
        """
        Solve linearized version using fractional Laplacian.

        Physical Meaning:
            Solves the linearized version of the BVP equation:
            L_β a = μ(-Δ)^β a + λa = s(x,φ,t)
            which provides a good initial guess for the full nonlinear equation.

        Mathematical Foundation:
            In spectral space: â(k) = ŝ(k) / (μ|k|^(2β) + λ)
            where k is the 7D wave vector.

        Args:
            source_field (np.ndarray): Source term s(x,φ,t).

        Returns:
            np.ndarray: Linearized solution a(x,φ,t).
        """
        from bhlff.core.operators.fractional_laplacian import FractionalLaplacian

        # Create fractional Laplacian operator
        fractional_laplacian = FractionalLaplacian(
            self.domain, self.parameters.beta, self.parameters.lambda_param
        )

        # Solve in spectral space
        from .spectral_operations import SpectralOperations

        spectral_ops = SpectralOperations(self.domain, self.parameters.precision)
        source_spectral = spectral_ops.forward_fft(
            source_field, normalization="physics"
        )
        spectral_coeffs = fractional_laplacian.get_spectral_coefficients()
        solution_spectral = source_spectral / spectral_coeffs
        solution = spectral_ops.inverse_fft(solution_spectral, normalization="physics")

        return solution.real
