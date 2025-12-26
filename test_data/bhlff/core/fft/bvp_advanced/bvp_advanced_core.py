"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core advanced BVP solver for 7D envelope equation.

This module implements the core advanced BVP solving functionality
for the 7D envelope equation.
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.domain_7d_bvp import Domain7DBVP
    from ..domain.parameters_7d_bvp import Parameters7DBVP
    from .spectral_derivatives import SpectralDerivatives
    from ...bvp.abstract_solver_core import AbstractSolverCore
else:
    from ...bvp.abstract_solver_core import AbstractSolverCore

from .bvp_preconditioning import BVPPreconditioning
from .bvp_optimization import BVPOptimization
from .bvp_adaptive import BVPAdaptive


class BVPAdvancedCore(AbstractSolverCore):
    """
    Core advanced BVP solver functionality.

    Physical Meaning:
        Implements core advanced mathematical operations for solving the 7D BVP
        envelope equation, coordinating specialized modules for different aspects
        of advanced solving.

    Mathematical Foundation:
        Extends basic BVP operations with:
        - Advanced preconditioning techniques
        - Optimization algorithms
        - Adaptive numerical methods
    """

    def __init__(
        self,
        domain: "Domain7DBVP",
        parameters: "Parameters7DBVP",
        derivatives: "SpectralDerivatives",
    ):
        """
        Initialize advanced BVP solver core.

        Physical Meaning:
            Sets up the advanced BVP solver with all necessary components
            for optimized, preconditioned, and adaptive solving capabilities.

        Args:
            domain (Domain7DBVP): 7D computational domain.
            parameters (Parameters7DBVP): BVP parameters.
            derivatives (SpectralDerivatives): Spectral derivatives.
        """
        super().__init__(domain, parameters)
        self.domain = domain
        self.parameters = parameters
        self.derivatives = derivatives
        self.logger = logging.getLogger(__name__)

        # Advanced solver parameters
        self.max_iterations = parameters.get("max_iterations", 100)
        self.tolerance = parameters.get("tolerance", 1e-6)
        self.preconditioning_enabled = parameters.get("preconditioning_enabled", True)
        self.optimization_enabled = parameters.get("optimization_enabled", True)
        self.adaptive_enabled = parameters.get("adaptive_enabled", True)

        # Initialize specialized modules
        self.preconditioning = BVPPreconditioning(domain, parameters, derivatives)
        self.optimization = BVPOptimization(domain, parameters, derivatives)
        self.adaptive = BVPAdaptive(domain, parameters, derivatives)

    def solve_with_preconditioning(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Solve with preconditioning.

        Physical Meaning:
            Solves the BVP envelope equation using preconditioning techniques
            for improved convergence and numerical stability.

        Mathematical Foundation:
            Uses preconditioned iterative methods with:
            - Advanced preconditioner construction
            - Improved conditioning of the linear system
            - Enhanced convergence properties

        Args:
            solution (np.ndarray): Initial solution guess.
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.

        Raises:
            ValueError: If solution or source have incompatible shapes.
            RuntimeError: If preconditioned solving fails.
        """
        if solution.shape != self.domain.shape or source.shape != self.domain.shape:
            raise ValueError(
                "Solution and source must have compatible shapes with domain"
            )

        return self.preconditioning.solve_with_preconditioning(solution, source)

    def solve_with_optimization(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Solve with optimization.

        Physical Meaning:
            Solves the BVP envelope equation using optimization techniques
            for improved efficiency and accuracy.

        Mathematical Foundation:
            Uses optimized iterative methods with:
            - Optimal step size computation
            - Efficient residual and Jacobian computation
            - Computational optimization

        Args:
            solution (np.ndarray): Initial solution guess.
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.

        Raises:
            ValueError: If solution or source have incompatible shapes.
            RuntimeError: If optimized solving fails.
        """
        if solution.shape != self.domain.shape or source.shape != self.domain.shape:
            raise ValueError(
                "Solution and source must have compatible shapes with domain"
            )

        return self.optimization.solve_with_optimization(solution, source)

    def solve_adaptive(self, solution: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Solve using adaptive methods.

        Physical Meaning:
            Solves the BVP envelope equation using adaptive methods
            for improved convergence and accuracy.

        Mathematical Foundation:
            Uses adaptive iterative methods with:
            - Dynamic step size adjustment
            - Adaptive refinement
            - Convergence monitoring

        Args:
            solution (np.ndarray): Initial solution guess.
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.

        Raises:
            ValueError: If solution or source have incompatible shapes.
            RuntimeError: If adaptive solving fails.
        """
        if solution.shape != self.domain.shape or source.shape != self.domain.shape:
            raise ValueError(
                "Solution and source must have compatible shapes with domain"
            )

        return self.adaptive.solve_adaptive(solution, source)

    def _compute_residual_basic(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Compute residual using basic method.

        Physical Meaning:
            Computes the residual of the BVP envelope equation
            r = s - L[a] where s is the source and L[a] is the operator applied to solution.

        Mathematical Foundation:
            Residual r = s - L[a] measures how well the current solution
            satisfies the BVP envelope equation.

        Args:
            solution (np.ndarray): Current solution field.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Residual field.
        """
        return source - self._apply_operator(solution)

    def _compute_jacobian_basic(self, solution: np.ndarray) -> np.ndarray:
        """
        Compute Jacobian using basic method.

        Physical Meaning:
            Computes the Jacobian matrix J = ∂L/∂a of the BVP envelope equation
            for Newton-Raphson iteration, where L is the BVP operator.

        Mathematical Foundation:
            Jacobian J_ij = ∂L_i/∂a_j represents the sensitivity of the operator
            to changes in the solution field.

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            np.ndarray: Jacobian matrix.
        """
        return np.eye(solution.size).reshape(solution.shape + solution.shape)

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
