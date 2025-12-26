"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP preconditioning for 7D envelope equation.

This module implements preconditioning functionality
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


class BVPPreconditioning:
    """
    BVP preconditioning for 7D envelope equation.

    Physical Meaning:
        Provides preconditioning functionality for BVP solving
        in the 7D envelope equation.
    """

    def __init__(
        self,
        domain: "Domain7DBVP",
        parameters: "Parameters7DBVP",
        derivatives: "SpectralDerivatives",
    ):
        """Initialize BVP preconditioning."""
        self.domain = domain
        self.parameters = parameters
        self.derivatives = derivatives
        self.logger = logging.getLogger(__name__)

    def solve_with_preconditioning(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Solve with preconditioning.

        Physical Meaning:
            Solves the BVP envelope equation using preconditioning techniques
            for improved convergence and numerical stability.

        Args:
            solution (np.ndarray): Initial solution guess.
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.
        """
        self.logger.info("Starting preconditioned BVP solving")

        # Preconditioned solving implementation
        max_iterations = self.parameters.get("max_iterations", 100)
        for iteration in range(max_iterations):
            # Compute residual
            residual = source - self._apply_operator(solution)

            # Check convergence
            residual_norm = np.linalg.norm(residual)
            if residual_norm < self.parameters.get("tolerance", 1e-6):
                break

            # Compute preconditioner
            preconditioner = self._compute_preconditioner(solution)

            # Apply preconditioning
            preconditioned_residual = preconditioner @ residual.flatten()

            # Update solution
            solution += preconditioned_residual.reshape(solution.shape)

        self.logger.info("Preconditioned BVP solving completed")
        return solution

    def _compute_preconditioner(self, solution: np.ndarray) -> np.ndarray:
        """
        Compute preconditioner matrix.
        
        Physical Meaning:
            Computes preconditioner matrix for improved convergence
            of the iterative solver.
            
        Args:
            solution (np.ndarray): Current solution field.
            
        Returns:
            np.ndarray: Preconditioner matrix.
        """
        n = solution.size
        preconditioner_scale = self.parameters.get("preconditioner_scale", 0.1)
        preconditioner = np.eye(n) * preconditioner_scale
        return preconditioner

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
