"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core advanced solver for 7D BVP envelope equation.

This module implements the core advanced solving functionality
for the 7D BVP envelope equation.
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from scipy.sparse import csc_matrix

from ....domain.domain_7d import Domain7D
from ...abstract_solver_core import AbstractSolverCore
from .solver_adaptive import SolverAdaptive
from .solver_optimized import SolverOptimized
from .solver_preconditioning import SolverPreconditioning


class SolverAdvancedCore(AbstractSolverCore):
    """
    Core advanced solver for 7D BVP envelope equation.

    Physical Meaning:
        Implements core advanced solving algorithms for the 7D envelope equation
        using adaptive methods, preconditioning, and optimization techniques
        for improved convergence and efficiency.

    Mathematical Foundation:
        Extends the basic Newton-Raphson method with:
        - Adaptive step size control
        - Preconditioning for better convergence
        - Optimization techniques for efficiency
    """

    def __init__(self, domain: Domain7D, config: Dict[str, Any]):
        """
        Initialize advanced 7D envelope solver core.

        Args:
            domain (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Solver configuration parameters.
        """
        super().__init__(domain, config)
        self.domain = domain
        self.config = config

        # Advanced solver parameters
        self.max_iterations = config.get("max_iterations", 100)
        self.tolerance = config.get("tolerance", 1e-6)
        self.adaptive_step_size = config.get("adaptive_step_size", True)
        self.preconditioning_enabled = config.get("preconditioning_enabled", True)
        self.optimization_enabled = config.get("optimization_enabled", True)

        # Initialize specialized modules
        self.adaptive = SolverAdaptive(domain, config)
        self.optimized = SolverOptimized(domain, config)
        self.preconditioning = SolverPreconditioning(domain, config)

    def solve_envelope_adaptive(self, source: np.ndarray) -> np.ndarray:
        """
        Solve envelope equation using adaptive methods.

        Physical Meaning:
            Solves the 7D envelope equation using adaptive step size control
            and preconditioning for improved convergence and stability.

        Mathematical Foundation:
            Uses adaptive Newton-Raphson method with:
            - Dynamic step size adjustment based on residual behavior
            - Preconditioning for better conditioning of the linear system
            - Convergence monitoring and adjustment

        Args:
            source (np.ndarray): Source term in the envelope equation.

        Returns:
            np.ndarray: Solution field satisfying the envelope equation.

        Raises:
            ValueError: If source has incompatible shape with domain.
            RuntimeError: If solver fails to converge.
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.adaptive.solve_adaptive(source)

    def solve_envelope_optimized(self, source: np.ndarray) -> np.ndarray:
        """
        Solve envelope equation using optimization techniques.

        Physical Meaning:
            Solves the 7D envelope equation using optimization techniques
            for improved efficiency and convergence.

        Mathematical Foundation:
            Uses optimized Newton-Raphson method with:
            - Optimized step size computation
            - Efficient residual and Jacobian computation
            - Memory and computational optimization

        Args:
            source (np.ndarray): Source term in the envelope equation.

        Returns:
            np.ndarray: Solution field satisfying the envelope equation.

        Raises:
            ValueError: If source has incompatible shape with domain.
            RuntimeError: If solver fails to converge.
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.optimized.solve_optimized(source)

    def _initialize_solution_adaptive(self, source: np.ndarray) -> np.ndarray:
        """
        Initialize solution for adaptive solving.

        Physical Meaning:
            Initializes the solution field for adaptive solving methods
            using intelligent initial guess based on source characteristics.

        Args:
            source (np.ndarray): Source term for initialization.

        Returns:
            np.ndarray: Initial solution guess.
        """
        return self.adaptive.initialize_solution(source)

    def _initialize_solution_optimized(self, source: np.ndarray) -> np.ndarray:
        """
        Initialize solution for optimized solving.

        Physical Meaning:
            Initializes the solution field for optimized solving methods
            using efficient initialization techniques.

        Args:
            source (np.ndarray): Source term for initialization.

        Returns:
            np.ndarray: Initial solution guess.
        """
        return self.optimized.initialize_solution(source)

    def _compute_residual_advanced(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Compute residual for advanced solving.

        Physical Meaning:
            Computes the residual of the envelope equation for advanced
            solving methods with enhanced accuracy and efficiency.

        Args:
            solution (np.ndarray): Current solution field.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Residual field.
        """
        return self.adaptive.compute_residual(solution, source)

    def _compute_residual_optimized(
        self, solution: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """
        Compute residual for optimized solving.

        Physical Meaning:
            Computes the residual of the envelope equation for optimized
            solving methods with computational efficiency.

        Args:
            solution (np.ndarray): Current solution field.
            source (np.ndarray): Source term.

        Returns:
            np.ndarray: Residual field.
        """
        return self.optimized.compute_residual(solution, source)

    def _compute_jacobian_advanced(self, solution: np.ndarray) -> csc_matrix:
        """
        Compute Jacobian for advanced solving.

        Physical Meaning:
            Computes the Jacobian matrix for advanced solving methods
            with enhanced accuracy and preconditioning support.

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            csc_matrix: Jacobian matrix in sparse format.
        """
        return self.adaptive.compute_jacobian(solution)

    def _compute_jacobian_optimized(self, solution: np.ndarray) -> csc_matrix:
        """
        Compute Jacobian for optimized solving.

        Physical Meaning:
            Computes the Jacobian matrix for optimized solving methods
            with computational efficiency and memory optimization.

        Args:
            solution (np.ndarray): Current solution field.

        Returns:
            csc_matrix: Jacobian matrix in sparse format.
        """
        return self.optimized.compute_jacobian(solution)

    def _solve_linear_system_advanced(
        self, jacobian: csc_matrix, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve linear system for advanced solving.

        Physical Meaning:
            Solves the linear system for advanced solving methods
            with preconditioning and adaptive techniques.

        Args:
            jacobian (csc_matrix): Jacobian matrix.
            residual (np.ndarray): Residual vector.

        Returns:
            np.ndarray: Solution update vector.
        """
        return self.adaptive.solve_linear_system(jacobian, residual)

    def _solve_linear_system_optimized(
        self, jacobian: csc_matrix, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve linear system for optimized solving.

        Physical Meaning:
            Solves the linear system for optimized solving methods
            with computational efficiency and memory optimization.

        Args:
            jacobian (csc_matrix): Jacobian matrix.
            residual (np.ndarray): Residual vector.

        Returns:
            np.ndarray: Solution update vector.
        """
        return self.optimized.solve_linear_system(jacobian, residual)

    def _apply_preconditioning(
        self, jacobian: csc_matrix, residual: np.ndarray
    ) -> Tuple[csc_matrix, np.ndarray]:
        """
        Apply preconditioning to linear system.

        Physical Meaning:
            Applies preconditioning to improve the conditioning of the
            linear system for better convergence.

        Args:
            jacobian (csc_matrix): Jacobian matrix.
            residual (np.ndarray): Residual vector.

        Returns:
            Tuple[csc_matrix, np.ndarray]: Preconditioned Jacobian and residual.
        """
        return self.preconditioning.apply_preconditioning(jacobian, residual)

    def _compute_preconditioner(self, jacobian: csc_matrix) -> csc_matrix:
        """
        Compute preconditioner matrix.

        Physical Meaning:
            Computes a preconditioner matrix to improve the conditioning
            of the linear system.

        Args:
            jacobian (csc_matrix): Jacobian matrix.

        Returns:
            csc_matrix: Preconditioner matrix.
        """
        return self.preconditioning.compute_preconditioner(jacobian)

    def _compute_adaptive_step_size(
        self, solution: np.ndarray, update: np.ndarray, residual: np.ndarray
    ) -> float:
        """
        Compute adaptive step size.

        Physical Meaning:
            Computes an adaptive step size based on the current solution,
            update vector, and residual for improved convergence.

        Args:
            solution (np.ndarray): Current solution field.
            update (np.ndarray): Solution update vector.
            residual (np.ndarray): Current residual.

        Returns:
            float: Adaptive step size.
        """
        return self.adaptive.compute_step_size(solution, update, residual)

    def _compute_optimized_step_size(
        self, solution: np.ndarray, update: np.ndarray, residual: np.ndarray
    ) -> float:
        """
        Compute optimized step size.

        Physical Meaning:
            Computes an optimized step size for efficient convergence
            using optimization techniques.

        Args:
            solution (np.ndarray): Current solution field.
            update (np.ndarray): Solution update vector.
            residual (np.ndarray): Current residual.

        Returns:
            float: Optimized step size.
        """
        return self.optimized.compute_step_size(solution, update, residual)

    def _adaptive_smooth_field(self, field: np.ndarray) -> np.ndarray:
        """
        Apply adaptive smoothing to field.

        Physical Meaning:
            Applies adaptive smoothing to the field for improved
            numerical stability and convergence.

        Args:
            field (np.ndarray): Field to smooth.

        Returns:
            np.ndarray: Smoothed field.
        """
        return self.adaptive.smooth_field(field)

    def _adaptive_scale_field(self, field: np.ndarray) -> np.ndarray:
        """
        Apply adaptive scaling to field.

        Physical Meaning:
            Applies adaptive scaling to the field for improved
            numerical conditioning and convergence.

        Args:
            field (np.ndarray): Field to scale.

        Returns:
            np.ndarray: Scaled field.
        """
        return self.adaptive.scale_field(field)

    def _optimized_smooth_field(self, field: np.ndarray) -> np.ndarray:
        """
        Apply optimized smoothing to field.

        Physical Meaning:
            Applies optimized smoothing to the field for improved
            efficiency and numerical stability.

        Args:
            field (np.ndarray): Field to smooth.

        Returns:
            np.ndarray: Smoothed field.
        """
        return self.optimized.smooth_field(field)

    def _optimized_scale_field(self, field: np.ndarray) -> np.ndarray:
        """
        Apply optimized scaling to field.

        Physical Meaning:
            Applies optimized scaling to the field for improved
            efficiency and numerical conditioning.

        Args:
            field (np.ndarray): Field to scale.

        Returns:
            np.ndarray: Scaled field.
        """
        return self.optimized.scale_field(field)
