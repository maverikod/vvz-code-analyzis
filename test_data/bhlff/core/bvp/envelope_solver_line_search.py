"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Line search algorithms for BVP envelope equation solver.

This module implements advanced line search algorithms for the Newton-Raphson
method used in solving the BVP envelope equation.

Physical Meaning:
    Provides line search algorithms to find optimal step sizes along
    Newton directions for robust convergence of the envelope equation solver.

Mathematical Foundation:
    Implements backtracking line search with Armijo condition and
    advanced step size selection algorithms.

Example:
    >>> line_search = EnvelopeSolverLineSearch()
    >>> step_size = line_search.perform_line_search(envelope, delta, residual, source)
"""

import numpy as np
from typing import Callable, Optional

from .bvp_constants import BVPConstants


class EnvelopeSolverLineSearch:
    """
    Line search algorithms for envelope equation solver.

    Physical Meaning:
        Implements advanced line search algorithms to find optimal step sizes
        along Newton directions for robust convergence.

    Mathematical Foundation:
        Provides backtracking line search with Armijo condition and
        advanced step size selection algorithms.
    """

    def __init__(self, constants: Optional[BVPConstants] = None) -> None:
        """
        Initialize line search algorithms.

        Args:
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.constants = constants or BVPConstants()
        self.max_iterations = int(
            self.constants.get_numerical_parameter("line_search_max_iter")
        )
        self.beta = self.constants.get_numerical_parameter("line_search_beta")
        self.gamma = self.constants.get_numerical_parameter("line_search_gamma")

    def perform_line_search(
        self,
        envelope: np.ndarray,
        delta_envelope: np.ndarray,
        residual: np.ndarray,
        source: np.ndarray,
        initial_step: float,
        residual_func: Callable[[np.ndarray, np.ndarray], np.ndarray],
    ) -> float:
        """
        Perform line search for optimal step size.

        Physical Meaning:
            Finds the optimal step size along the Newton direction
            to minimize the residual norm.

        Mathematical Foundation:
            Minimizes ||r(a + α*δa)||² with respect to α using
            backtracking line search.

        Args:
            envelope (np.ndarray): Current envelope estimate.
            delta_envelope (np.ndarray): Newton update direction.
            residual (np.ndarray): Current residual.
            source (np.ndarray): Source term.
            initial_step (float): Initial step size.
            residual_func (Callable): Function to compute residual.

        Returns:
            float: Optimal step size.
        """
        # Backtracking line search parameters
        alpha = initial_step

        # Current residual norm
        current_norm = np.sum(np.abs(residual) ** 2)

        # Armijo condition
        for _ in range(self.max_iterations):
            # Try new step
            new_envelope = envelope + alpha * delta_envelope
            new_residual = residual_func(new_envelope, source)
            new_norm = np.sum(np.abs(new_residual) ** 2)

            # Check Armijo condition
            if new_norm <= current_norm + self.gamma * alpha * np.real(
                np.sum(residual.conj() * delta_envelope)
            ):
                return alpha

            # Reduce step size
            alpha *= self.beta

        return alpha

    def perform_wolfe_line_search(
        self,
        envelope: np.ndarray,
        delta_envelope: np.ndarray,
        residual: np.ndarray,
        source: np.ndarray,
        initial_step: float,
        residual_func: Callable[[np.ndarray, np.ndarray], np.ndarray],
    ) -> float:
        """
        Perform Wolfe line search for optimal step size.

        Physical Meaning:
            Finds the optimal step size using Wolfe conditions for
            more robust convergence.

        Mathematical Foundation:
            Uses both Armijo condition and curvature condition:
            - Armijo: f(x + αp) ≤ f(x) + c₁α∇f(x)ᵀp
            - Curvature: ∇f(x + αp)ᵀp ≥ c₂∇f(x)ᵀp

        Args:
            envelope (np.ndarray): Current envelope estimate.
            delta_envelope (np.ndarray): Newton update direction.
            residual (np.ndarray): Current residual.
            source (np.ndarray): Source term.
            initial_step (float): Initial step size.
            residual_func (Callable): Function to compute residual.

        Returns:
            float: Optimal step size.
        """
        c1 = self.constants.get_numerical_parameter("armijo_c1")  # Armijo parameter
        c2 = self.constants.get_numerical_parameter(
            "curvature_c2"
        )  # Curvature parameter

        alpha = initial_step
        alpha_max = 1.0

        # Current residual norm and gradient
        current_norm = np.sum(np.abs(residual) ** 2)
        current_gradient = np.real(np.sum(residual.conj() * delta_envelope))

        for _ in range(self.max_iterations):
            # Try new step
            new_envelope = envelope + alpha * delta_envelope
            new_residual = residual_func(new_envelope, source)
            new_norm = np.sum(np.abs(new_residual) ** 2)

            # Check Armijo condition
            armijo_condition = new_norm <= current_norm + c1 * alpha * current_gradient

            if armijo_condition:
                # Check curvature condition
                new_gradient = np.real(np.sum(new_residual.conj() * delta_envelope))
                curvature_condition = new_gradient >= c2 * current_gradient

                if curvature_condition:
                    return alpha

            # Update step size
            if alpha < alpha_max:
                alpha = min(2 * alpha, alpha_max)
            else:
                alpha *= self.beta

        return alpha

    def perform_adaptive_line_search(
        self,
        envelope: np.ndarray,
        delta_envelope: np.ndarray,
        residual: np.ndarray,
        source: np.ndarray,
        initial_step: float,
        residual_func: Callable[[np.ndarray, np.ndarray], np.ndarray],
    ) -> float:
        """
        Perform adaptive line search with dynamic parameters.

        Physical Meaning:
            Adapts line search parameters based on convergence history
            for optimal performance.

        Mathematical Foundation:
            Dynamically adjusts line search parameters based on
            convergence behavior and problem characteristics.

        Args:
            envelope (np.ndarray): Current envelope estimate.
            delta_envelope (np.ndarray): Newton update direction.
            residual (np.ndarray): Current residual.
            source (np.ndarray): Source term.
            initial_step (float): Initial step size.
            residual_func (Callable): Function to compute residual.

        Returns:
            float: Optimal step size.
        """
        # Adaptive parameters based on residual norm
        residual_norm = np.max(np.abs(residual))

        if residual_norm > 1e-3:
            # Large residual - use conservative line search
            gamma = 1e-3
            beta = 0.3
        elif residual_norm > 1e-6:
            # Medium residual - use moderate line search
            gamma = 1e-4
            beta = 0.5
        else:
            # Small residual - use aggressive line search
            gamma = 1e-5
            beta = 0.7

        alpha = initial_step
        current_norm = np.sum(np.abs(residual) ** 2)

        for _ in range(self.max_iterations):
            # Try new step
            new_envelope = envelope + alpha * delta_envelope
            new_residual = residual_func(new_envelope, source)
            new_norm = np.sum(np.abs(new_residual) ** 2)

            # Check Armijo condition with adaptive parameters
            if new_norm <= current_norm + gamma * alpha * np.real(
                np.sum(residual.conj() * delta_envelope)
            ):
                return alpha

            # Reduce step size with adaptive factor
            alpha *= beta

        return alpha
