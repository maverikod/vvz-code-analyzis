"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for 7D BVP envelope equation.

This module provides a unified interface for the 7D BVP envelope equation,
coordinating all components through a single facade class for solving
the full 7D envelope equation.

Physical Meaning:
    The envelope equation facade provides a unified interface to solve
    the full 7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
    including spatial, phase, and temporal derivatives with nonlinear terms.

Mathematical Foundation:
    Solves the 7D envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    using modular derivative operators, nonlinear terms, and iterative
    Newton-Raphson solver.

Example:
    >>> equation_7d = BVPEnvelopeEquation7D(domain_7d, config)
    >>> envelope = equation_7d.solve_envelope(source_7d)
"""

import numpy as np
from typing import Dict, Any, Optional

from ...domain.domain_7d import Domain7D
from ..bvp_constants import BVPConstants
from .derivative_operators_facade import DerivativeOperators7D
from .nonlinear_terms import NonlinearTerms7D
from .solver_core import EnvelopeSolverCore7D

# ResidualComputer removed - functionality moved to AbstractSolverCore


class BVPEnvelopeEquation7D:
    """
    7D BVP envelope equation solver.

    Physical Meaning:
        Solves the full 7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
        including spatial, phase, and temporal derivatives with nonlinear
        stiffness and susceptibility terms.

    Mathematical Foundation:
        Solves the 7D envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
        where:
        - κ(|a|) = κ₀ + κ₂|a|² (nonlinear stiffness)
        - χ(|a|) = χ' + iχ''(|a|) (effective susceptibility with quenches)
        - s(x,φ,t) is the source term
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize 7D envelope equation solver.

        Physical Meaning:
            Sets up the envelope equation solver with the computational
            domain and configuration parameters, initializing all
            necessary components for solving the 7D equation.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - kappa_0, kappa_2: Stiffness coefficients
                - chi_prime, chi_double_prime_0: Susceptibility coefficients
                - k0: Wave number
                - max_iterations: Maximum Newton-Raphson iterations
                - tolerance: Convergence tolerance
        """
        self.domain_7d = domain_7d
        self.config = config

        # Initialize modular components
        self.derivative_operators = DerivativeOperators7D(domain_7d)
        self.nonlinear_terms = NonlinearTerms7D(domain_7d, config)
        self.solver_core = EnvelopeSolverCore7D(domain_7d, config)
        self.residual_computer = EnvelopeSolverCore7D(domain_7d, config)

        # Setup components
        self.derivative_operators.setup_operators()
        self.nonlinear_terms.setup_terms()

        # Solver parameters
        self.max_iterations = config.get("max_iterations", 100)
        self.tolerance = config.get("tolerance", 1e-8)

    def solve_envelope(
        self, source_7d: np.ndarray, initial_guess: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Solve 7D envelope equation.

        Physical Meaning:
            Solves the full 7D envelope equation for the BVP field
            in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ using iterative
            Newton-Raphson method for nonlinear terms.

        Mathematical Foundation:
            Solves: ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
            using iterative Newton-Raphson method for nonlinear terms.

        Args:
            source_7d (np.ndarray): 7D source term s(x,φ,t).
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)
            initial_guess (Optional[np.ndarray]): Initial guess for solution.
                If None, uses zero initial guess.

        Returns:
            np.ndarray: 7D envelope solution a(x,φ,t).
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)
        """

        # Define residual function
        def residual_func(envelope, source):
            return self.residual_computer.compute_residual(
                envelope, source, self.derivative_operators, self.nonlinear_terms
            )

        # Define Jacobian function
        def jacobian_func(envelope):
            amplitude = np.abs(envelope)
            dkappa_da = self.nonlinear_terms.compute_stiffness_derivative(amplitude)
            dchi_da = self.nonlinear_terms.compute_susceptibility_derivative(amplitude)
            return self.solver_core.compute_jacobian_sparse(
                envelope,
                dkappa_da,
                dchi_da,
                self.derivative_operators,
                self.nonlinear_terms,
            )

        # Solve using solver core
        return self.solver_core.solve_envelope(source_7d, initial_guess)

    def get_parameters(self) -> Dict[str, float]:
        """
        Get envelope equation parameters.

        Physical Meaning:
            Returns the current values of all parameters for
            monitoring and analysis purposes.

        Returns:
            Dict[str, float]: Dictionary containing all parameters.
        """
        params = self.nonlinear_terms.get_parameters()
        solver_params = self.solver_core.get_solver_parameters()
        params.update(solver_params)
        return params

    def analyze_solution_quality(
        self, envelope: np.ndarray, source: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze quality of the solution.

        Physical Meaning:
            Analyzes the quality of the envelope solution by computing
            residual components and convergence metrics.

        Args:
            envelope (np.ndarray): Computed envelope solution.
            source (np.ndarray): Source term.

        Returns:
            Dict[str, Any]: Dictionary containing solution quality analysis.
        """
        # Compute residual
        residual = self.residual_computer.compute_residual(
            envelope, source, self.derivative_operators, self.nonlinear_terms
        )

        # Analyze residual components
        component_analysis = self.residual_computer.analyze_residual_components(
            envelope, source, self.derivative_operators, self.nonlinear_terms
        )

        # Compute residual norm
        residual_norm = self.residual_computer.compute_residual_norm(residual)

        return {
            "residual_norm": residual_norm,
            "convergence_achieved": residual_norm < self.tolerance,
            "component_analysis": component_analysis,
            "solution_quality": "good" if residual_norm < self.tolerance else "poor",
        }

    def __repr__(self) -> str:
        """
        String representation of envelope equation solver.

        Returns:
            str: String representation showing domain and parameters.
        """
        return (
            f"BVPEnvelopeEquation7D(domain_7d={self.domain_7d}, "
            f"max_iterations={self.max_iterations}, tolerance={self.tolerance})"
        )
