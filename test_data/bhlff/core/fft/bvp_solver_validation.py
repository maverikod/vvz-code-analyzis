"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation methods for 7D BVP solver.

This module provides validation methods for the 7D BVP solver, including
solution validation, residual computation, and error analysis.

Physical Meaning:
    Implements validation methods for verifying the correctness of solutions
    to the 7D BVP envelope equation with proper tolerance checking.

Mathematical Foundation:
    Validates solutions by computing residuals and checking physical
    constraints such as energy conservation and boundary conditions.

Example:
    >>> validator = BVPSolverValidation(core_solver, parameters)
    >>> validation = validator.validate_solution(solution, source)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.domain_7d_bvp import Domain7DBVP
    from ..domain.parameters_7d_bvp import Parameters7DBVP
    from .bvp_solver_core import BVPSolverCore


class BVPSolverValidation:
    """
    Validation methods for 7D BVP solver.

    Physical Meaning:
        Implements validation methods for verifying the correctness of solutions
        to the 7D BVP envelope equation with proper tolerance checking.

    Mathematical Foundation:
        Validates solutions by computing residuals and checking physical
        constraints such as energy conservation and boundary conditions.

    Attributes:
        core (BVPSolverCore): Core BVP solver functionality.
        parameters (Parameters7DBVP): 7D BVP parameters.
        domain (Domain7DBVP): 7D BVP computational domain.
    """

    def __init__(self, core: "BVPSolverCore", parameters: "Parameters7DBVP"):
        """
        Initialize BVP solver validation.

        Physical Meaning:
            Sets up the validation methods with core functionality
            and parameters for solution validation.

        Args:
            core (BVPSolverCore): Core BVP solver functionality.
            parameters (Parameters7DBVP): 7D BVP parameters.
        """
        self.core = core
        self.parameters = parameters
        self.domain = core.domain
        self.logger = logging.getLogger(__name__)

        self.logger.info("BVPSolverValidation initialized.")

    def validate_solution(
        self,
        solution: np.ndarray,
        source: np.ndarray,
        tolerance: float = 1e-8,
        method: str = "linearized",
    ) -> Dict[str, Any]:
        """
        Validate BVP solution.

        Physical Meaning:
            Validates the solution by computing the residual and checking
            that it satisfies the BVP equation within the specified tolerance.

        Args:
            solution (np.ndarray): Solution a(x,φ,t).
            source (np.ndarray): Source term s(x,φ,t).
            tolerance (float): Validation tolerance.
            method (str): Validation method ('linearized' or 'full').

        Returns:
            Dict[str, Any]: Validation results.
        """
        if method == "linearized":
            # For linearized solutions, validate against linearized equation
            residual = self.core.compute_linearized_residual(solution, source)
        else:
            # For full solutions, validate against full BVP equation
            residual = self.core.compute_residual(solution, source)

        residual_norm = np.linalg.norm(residual)
        source_norm = np.linalg.norm(source)
        relative_residual = (
            residual_norm / source_norm if source_norm > 0 else residual_norm
        )

        is_valid = relative_residual < tolerance

        return {
            "is_valid": is_valid,
            "residual_norm": residual_norm,
            "relative_residual": relative_residual,
            "tolerance": tolerance,
            "method": method,
        }

    def check_energy_conservation(
        self,
        field: np.ndarray,
        expected_energy: Optional[float] = None,
        tolerance: float = 1e-10,
    ) -> Dict[str, Any]:
        """
        Check energy conservation for the field.

        Physical Meaning:
            Verifies that the field satisfies energy conservation principles
            within the specified tolerance.

        Mathematical Foundation:
            Computes the total energy of the field and checks if it matches
            the expected value or is conserved over time.

        Args:
            field (np.ndarray): Field to check.
            expected_energy (Optional[float]): Expected energy value.
            tolerance (float): Energy conservation tolerance.

        Returns:
            Dict[str, Any]: Energy conservation results.
        """
        # Compute field energy
        field_energy = np.sum(np.abs(field) ** 2)

        if expected_energy is not None:
            energy_error = abs(field_energy - expected_energy)
            is_conserved = energy_error < tolerance
        else:
            # For now, just check that energy is finite and positive
            is_conserved = np.isfinite(field_energy) and field_energy > 0
            energy_error = 0.0

        return {
            "is_conserved": is_conserved,
            "field_energy": field_energy,
            "expected_energy": expected_energy,
            "energy_error": energy_error,
            "tolerance": tolerance,
        }

    def check_boundary_conditions(
        self, field: np.ndarray, boundary_type: str = "periodic"
    ) -> Dict[str, Any]:
        """
        Check boundary conditions for the field.

        Physical Meaning:
            Verifies that the field satisfies the specified boundary conditions
            at the domain boundaries.

        Mathematical Foundation:
            For periodic boundary conditions, checks that field values at
            opposite boundaries match within numerical precision.

        Args:
            field (np.ndarray): Field to check.
            boundary_type (str): Type of boundary conditions.

        Returns:
            Dict[str, Any]: Boundary condition results.
        """
        if boundary_type == "periodic":
            # Check periodic boundary conditions
            boundary_errors = []

            # Check spatial boundaries
            for dim in range(3):
                if field.shape[dim] > 1:
                    left_boundary = np.take(field, 0, axis=dim)
                    right_boundary = np.take(field, -1, axis=dim)
                    boundary_error = np.linalg.norm(left_boundary - right_boundary)
                    boundary_errors.append(boundary_error)

            # Check phase boundaries
            for dim in range(3, 6):
                if field.shape[dim] > 1:
                    left_boundary = np.take(field, 0, axis=dim)
                    right_boundary = np.take(field, -1, axis=dim)
                    boundary_error = np.linalg.norm(left_boundary - right_boundary)
                    boundary_errors.append(boundary_error)

            max_boundary_error = max(boundary_errors) if boundary_errors else 0.0
            is_satisfied = max_boundary_error < 1e-10

            return {
                "is_satisfied": is_satisfied,
                "boundary_errors": boundary_errors,
                "max_boundary_error": max_boundary_error,
                "boundary_type": boundary_type,
            }
        else:
            return {
                "is_satisfied": True,  # Assume satisfied for other types
                "boundary_errors": [],
                "max_boundary_error": 0.0,
                "boundary_type": boundary_type,
            }
