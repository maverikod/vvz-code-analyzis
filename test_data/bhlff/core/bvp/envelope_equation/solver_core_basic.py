"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic solver core for 7D BVP envelope equation.

This module implements the basic solving algorithms for the 7D BVP envelope
equation, including core Newton-Raphson iterations and linear system solving.
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from scipy.sparse import csc_matrix, lil_matrix

from ...domain.domain_7d import Domain7D
from ..abstract_solver_core import AbstractSolverCore


class EnvelopeSolverCoreBasic(AbstractSolverCore):
    """
    Basic solver core for 7D BVP envelope equation.

    Physical Meaning:
        Implements the basic solving algorithms for the 7D envelope equation
        using Newton-Raphson iterations for nonlinear terms and sparse
        linear system solving for the linearized equations.

    Mathematical Foundation:
        Solves the 7D envelope equation using Newton-Raphson method:
        1. Compute residual R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s
        2. Compute Jacobian J = ∂R/∂a
        3. Solve J·δa = -R for update δa
        4. Update solution a ← a - δa
        5. Repeat until convergence
    """

    def __init__(self, domain: Domain7D, config: Dict[str, Any]):
        """
        Initialize 7D envelope solver core.

        Physical Meaning:
            Sets up the solver core with the 7D computational domain
            and configuration parameters for solving the envelope equation.

        Args:
            domain (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Solver configuration parameters.
        """
        super().__init__(domain, config)
        self.domain = domain
        self.config = config

        # Solver parameters
        self.max_iterations = config.get("max_iterations", 100)
        self.tolerance = config.get("tolerance", 1e-6)
        self.relaxation_factor = config.get("relaxation_factor", 1.0)

        # Initialize solver state
        self.current_iteration = 0
        self.current_residual = float("inf")
        self.convergence_history = []

    def solve_envelope(self, source: np.ndarray) -> np.ndarray:
        """
        Solve the 7D envelope equation.

        Physical Meaning:
            Solves the 7D envelope equation for the given source term,
            representing the numerical solution of field evolution in
            7D space-time.

        Mathematical Foundation:
            Uses Newton-Raphson iteration to solve:
            ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)

        Args:
            source (np.ndarray): 7D source term s(x,φ,t).

        Returns:
            np.ndarray: 7D solution field a(x,φ,t).
        """
        # Initialize solution
        solution = self._initialize_solution(source)

        # Newton-Raphson iteration
        for iteration in range(self.max_iterations):
            self.current_iteration = iteration

            # Compute residual
            residual = self._compute_residual(solution, source)
            self.current_residual = np.linalg.norm(residual)

            # Check convergence
            if self.current_residual < self.tolerance:
                break

            # Compute Jacobian
            jacobian = self._compute_jacobian(solution)

            # Solve linear system
            update = self._solve_linear_system(jacobian, residual)

            # Update solution
            solution = solution - self.relaxation_factor * update

            # Store convergence history
            self.convergence_history.append(self.current_residual)

        return solution

    def _initialize_solution(self, source: np.ndarray) -> np.ndarray:
        """
        Initialize solution field.

        Physical Meaning:
            Initializes the solution field with an appropriate initial guess,
            typically based on the source term or previous solutions.

        Args:
            source (np.ndarray): 7D source term.

        Returns:
            np.ndarray: Initial solution field.
        """
        # Simple initialization based on source
        initial_solution = source.copy()

        # Apply smoothing to avoid singularities
        initial_solution = self._smooth_field(initial_solution)

        return initial_solution

    def _compute_residual(self, solution: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute residual of the envelope equation.

        Physical Meaning:
            Computes the residual R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s,
            which measures how well the current solution satisfies
            the envelope equation.

        Mathematical Foundation:
            R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s(x,φ,t)

        Args:
            solution (np.ndarray): Current solution field.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Residual field.
        """
        # Compute nonlinear stiffness κ(|a|)
        stiffness = self._compute_nonlinear_stiffness(solution)

        # Compute effective susceptibility χ(|a|)
        susceptibility = self._compute_effective_susceptibility(solution)

        # Compute divergence term ∇·(κ(|a|)∇a)
        divergence_term = self._compute_divergence_term(solution, stiffness)

        # Compute susceptibility term k₀²χ(|a|)a
        susceptibility_term = self._compute_susceptibility_term(
            solution, susceptibility
        )

        # Compute residual
        residual = divergence_term + susceptibility_term - source

        return residual

    def _compute_jacobian(self, solution: np.ndarray) -> csc_matrix:
        """
        Compute Jacobian matrix.

        Physical Meaning:
            Computes the Jacobian matrix J = ∂R/∂a, which represents
            the linearization of the residual around the current solution.

        Mathematical Foundation:
            J = ∂/∂a[∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s]

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            csc_matrix: Jacobian matrix in sparse format.
        """
        # Get field dimensions
        field_shape = solution.shape
        total_points = solution.size

        # Initialize Jacobian matrix
        jacobian = lil_matrix((total_points, total_points))

        # Compute Jacobian entries
        for i in range(total_points):
            # Get multi-dimensional index
            idx = np.unravel_index(i, field_shape)

            # Compute Jacobian row
            jacobian_row = self._compute_jacobian_row(solution, idx)

            # Set Jacobian entries
            for j, value in jacobian_row.items():
                jacobian[i, j] = value

        return jacobian.tocsc()

    def _solve_linear_system(
        self, jacobian: csc_matrix, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve linear system J·δa = -R.

        Physical Meaning:
            Solves the linearized system to find the update δa
            for the Newton-Raphson iteration.

        Args:
            jacobian (csc_matrix): Jacobian matrix.
            residual (np.ndarray): Residual vector.

        Returns:
            np.ndarray: Update vector δa.
        """
        # Solve linear system
        from scipy.sparse.linalg import spsolve

        # Reshape residual to vector
        residual_vector = residual.flatten()

        # Solve J·δa = -R
        update_vector = spsolve(jacobian, -residual_vector)

        # Reshape back to field shape
        update = update_vector.reshape(residual.shape)

        return update

    def _smooth_field(self, field: np.ndarray) -> np.ndarray:
        """
        Apply smoothing to field to avoid singularities.

        Args:
            field (np.ndarray): Field to smooth.

        Returns:
            np.ndarray: Smoothed field.
        """
        # Simple smoothing using convolution
        from scipy.ndimage import gaussian_filter

        smoothed_field = gaussian_filter(field, sigma=0.5)

        return smoothed_field

    def _compute_nonlinear_stiffness(self, solution: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear stiffness κ(|a|).

        Physical Meaning:
            Computes the nonlinear stiffness coefficient that depends
            on the field amplitude, representing the field's response
            to spatial variations.

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            np.ndarray: Nonlinear stiffness field.
        """
        # Simple nonlinear stiffness model
        amplitude = np.abs(solution)
        stiffness = 1.0 + 0.1 * amplitude**2

        return stiffness

    def _compute_effective_susceptibility(self, solution: np.ndarray) -> np.ndarray:
        """
        Compute effective susceptibility χ(|a|).

        Physical Meaning:
            Computes the effective susceptibility that depends on
            the field amplitude, representing the field's response
            to external excitations.

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            np.ndarray: Effective susceptibility field.
        """
        # Simple effective susceptibility model
        amplitude = np.abs(solution)
        susceptibility = 1.0 + 0.05 * amplitude**2

        return susceptibility

    def _compute_divergence_term(
        self, solution: np.ndarray, stiffness: np.ndarray
    ) -> np.ndarray:
        """
        Compute divergence term ∇·(κ(|a|)∇a).

        Physical Meaning:
            Computes the divergence of the stiffness-weighted gradient,
            representing the spatial variation of the field.

        Args:
            solution (np.ndarray): Current solution field.
            stiffness (np.ndarray): Nonlinear stiffness field.

        Returns:
            np.ndarray: Divergence term.
        """
        # Compute gradient
        gradient = self._compute_gradient(solution)

        # Compute stiffness-weighted gradient
        weighted_gradient = stiffness[..., np.newaxis] * gradient

        # Compute divergence
        divergence = self._compute_divergence(weighted_gradient)

        return divergence

    def _compute_susceptibility_term(
        self, solution: np.ndarray, susceptibility: np.ndarray
    ) -> np.ndarray:
        """
        Compute susceptibility term k₀²χ(|a|)a.

        Physical Meaning:
            Computes the susceptibility-weighted field term,
            representing the field's response to external excitations.

        Args:
            solution (np.ndarray): Current solution field.
            susceptibility (np.ndarray): Effective susceptibility field.

        Returns:
            np.ndarray: Susceptibility term.
        """
        # Get wavenumber from config
        k0 = self.config.get("wavenumber", 1.0)

        # Compute susceptibility term
        susceptibility_term = k0**2 * susceptibility * solution

        return susceptibility_term

    def _compute_gradient(self, field: np.ndarray) -> np.ndarray:
        """
        Compute gradient of field.

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            np.ndarray: Gradient field.
        """
        # Compute gradient using finite differences
        gradient = np.gradient(field)

        # Stack gradients along new axis
        gradient = np.stack(gradient, axis=-1)

        return gradient

    def _compute_divergence(self, vector_field: np.ndarray) -> np.ndarray:
        """
        Compute divergence of vector field.

        Args:
            vector_field (np.ndarray): Vector field to differentiate.

        Returns:
            np.ndarray: Divergence field.
        """
        # Compute divergence using finite differences
        divergence = np.zeros(vector_field.shape[:-1])

        for i in range(vector_field.shape[-1]):
            divergence += np.gradient(vector_field[..., i])[i]

        return divergence

    def _compute_jacobian_row(
        self, solution: np.ndarray, idx: Tuple[int, ...]
    ) -> Dict[int, float]:
        """
        Compute Jacobian row for a specific point.

        Args:
            solution (np.ndarray): Current solution field.
            idx (Tuple[int, ...]): Multi-dimensional index.

        Returns:
            Dict[int, float]: Jacobian row entries.
        """
        # Simplified Jacobian computation
        jacobian_row = {}

        # Get field shape
        field_shape = solution.shape
        total_points = solution.size

        # Convert index to linear index
        linear_idx = np.ravel_multi_index(idx, field_shape)

        # Set diagonal entry
        jacobian_row[linear_idx] = 1.0

        # Set off-diagonal entries for neighboring points
        for dim in range(len(idx)):
            for offset in [-1, 1]:
                neighbor_idx = list(idx)
                neighbor_idx[dim] += offset

                # Check bounds
                if 0 <= neighbor_idx[dim] < field_shape[dim]:
                    neighbor_linear_idx = np.ravel_multi_index(
                        neighbor_idx, field_shape
                    )
                    jacobian_row[neighbor_linear_idx] = -0.1

        return jacobian_row

    def get_convergence_info(self) -> Dict[str, Any]:
        """
        Get convergence information.

        Returns:
            Dict[str, Any]: Convergence information.
        """
        return {
            "iterations": self.current_iteration,
            "final_residual": self.current_residual,
            "convergence_history": self.convergence_history,
            "converged": self.current_residual < self.tolerance,
        }
