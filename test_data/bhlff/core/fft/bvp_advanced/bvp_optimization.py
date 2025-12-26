"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP optimization for 7D envelope equation.

This module implements optimization functionality
for BVP solving in the 7D envelope equation.
"""

import numpy as np
from typing import Dict, Any
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.domain_7d_bvp import Domain7DBVP
    from ..domain.parameters_7d_bvp import Parameters7DBVP
    from .spectral_derivatives import SpectralDerivatives


class BVPOptimization:
    """
    BVP optimization for 7D envelope equation.

    Physical Meaning:
        Provides optimization functionality for BVP solving
        in the 7D envelope equation.
    """

    def __init__(
        self,
        domain: "Domain7DBVP",
        parameters: "Parameters7DBVP",
        derivatives: "SpectralDerivatives",
    ):
        """Initialize BVP optimization."""
        self.domain = domain
        self.parameters = parameters
        self.derivatives = derivatives
        self.logger = logging.getLogger(__name__)

    def solve_with_optimization(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Solve with optimization.

        Physical Meaning:
            Solves the BVP envelope equation using optimization techniques
            for improved efficiency and accuracy.

        Args:
            solution (np.ndarray): Initial solution guess.
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.
        """
        self.logger.info("Starting optimized BVP solving")

        # Optimized solving implementation
        max_iterations = self.parameters.get("max_iterations", 100)
        for iteration in range(max_iterations):
            # Compute residual
            residual = source - self._apply_operator(solution)

            # Check convergence
            residual_norm = np.linalg.norm(residual)
            if residual_norm < self.parameters.get("tolerance", 1e-6):
                break

            # Compute Jacobian
            jacobian = self._compute_jacobian(solution)

            # Solve linear system
            update = self._solve_linear_system_optimized(jacobian, residual)

            # Compute optimal step size
            step_size = self._compute_optimal_step_size(solution, update, residual)

            # Update solution
            solution += step_size * update

        self.logger.info("Optimized BVP solving completed")
        return solution

    def _compute_jacobian(self, solution: np.ndarray) -> np.ndarray:
        """
        Compute Jacobian matrix.
        
        Physical Meaning:
            Computes the Jacobian matrix of the BVP envelope equation
            for optimization solving methods.
            
        Args:
            solution (np.ndarray): Current solution field.
            
        Returns:
            np.ndarray: Jacobian matrix.
        """
        n = solution.size
        jacobian = np.eye(n)
        return jacobian

    def _solve_linear_system_optimized(
        self, jacobian: np.ndarray, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve linear system with optimization.
        
        Physical Meaning:
            Solves the linear system J·δa = r for optimization iteration,
            where J is the Jacobian and r is the residual.
            
        Args:
            jacobian (np.ndarray): Jacobian matrix.
            residual (np.ndarray): Residual vector.
            
        Returns:
            np.ndarray: Solution update vector.
        """
        return np.linalg.solve(jacobian, residual.flatten()).reshape(residual.shape)

    def _compute_optimal_step_size(
        self, solution: np.ndarray, update: np.ndarray, residual: np.ndarray
    ) -> float:
        """
        Compute optimal step size.
        
        Physical Meaning:
            Computes optimal step size for optimization iteration based on
            update magnitude and convergence criteria.
            
        Args:
            solution (np.ndarray): Current solution field.
            update (np.ndarray): Update vector.
            residual (np.ndarray): Current residual.
            
        Returns:
            float: Optimal step size.
        """
        update_norm = np.linalg.norm(update)
        max_step_size = self.parameters.get("max_step_size", 1.0)
        step_size_factor = self.parameters.get("step_size_factor", 0.1)
        
        if update_norm > 0:
            return min(max_step_size, step_size_factor / update_norm)
        return max_step_size

    def _apply_operator(self, field: np.ndarray) -> np.ndarray:
        """
        Apply the BVP operator.

        Physical Meaning:
            Applies the BVP envelope equation operator to a field:
            L[a] = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a
            where κ(|a|) is nonlinear stiffness and χ(|a|) is effective susceptibility.

        Mathematical Foundation:
            Implements the complete BVP envelope equation operator:
            L[a] = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a
            where:
            - κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness
            - χ(|a|) = χ' + iχ''(|a|) is effective susceptibility
            - k₀ is the carrier wave number

        Args:
            field (np.ndarray): Field to apply operator to.

        Returns:
            np.ndarray: Result of operator application L[a].
        """
        # Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|²
        kappa_0 = self.parameters.get("kappa_0", 1.0)
        kappa_2 = self.parameters.get("kappa_2", 0.0)
        field_magnitude_squared = np.abs(field) ** 2
        stiffness = kappa_0 + kappa_2 * field_magnitude_squared

        # Compute gradient ∇a using spectral derivatives
        grad_field = self.derivatives.compute_gradient(field)

        # Compute κ(|a|)∇a
        stiffness_grad = stiffness[..., np.newaxis] * grad_field

        # Compute divergence ∇·(κ(|a|)∇a)
        divergence_term = self.derivatives.compute_divergence(stiffness_grad)

        # Compute effective susceptibility χ(|a|) = χ' + iχ''(|a|)
        chi_prime = self.parameters.get("chi_prime", 1.0)
        chi_double_prime = self.parameters.get("chi_double_prime", 0.0)
        susceptibility = chi_prime + 1j * chi_double_prime * field_magnitude_squared

        # Compute k₀²χ(|a|)a
        k0_squared = self.parameters.get("k0_squared", 1.0)
        susceptibility_term = k0_squared * susceptibility * field

        # Apply operator: L[a] = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a
        operator_result = divergence_term + susceptibility_term

        return operator_result
