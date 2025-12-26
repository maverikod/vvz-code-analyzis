"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation methods for 7D FFT Solver.

This module provides validation methods for the 7D phase field theory,
including solution validation, residual computation, and error analysis.

Physical Meaning:
    Implements validation methods for verifying the correctness of solutions
    to the fractional Laplacian equation L_β a = s(x) in 7D space-time.

Mathematical Foundation:
    Validates solutions by computing residuals and checking physical
    constraints such as energy conservation and boundary conditions.

Example:
    >>> solver = FFTSolver7D(domain, parameters)
    >>> solution = solver.solve_stationary(source_field)
    >>> residual = solver.validate_solution(solution, source_field)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import Domain
    from ..domain.parameters import Parameters


class FFTSolverValidation:
    """
    Validation methods for 7D FFT Solver.

    Physical Meaning:
        Implements validation methods for verifying the correctness of solutions
        to the fractional Laplacian equation L_β a = s(x) in 7D space-time.

    Mathematical Foundation:
        Validates solutions by computing residuals and checking physical
        constraints such as energy conservation and boundary conditions.

    Attributes:
        domain (Domain): Computational domain for the simulation.
        parameters (Parameters): Solver parameters.
        _fractional_laplacian: Fractional Laplacian operator.
    """

    def __init__(
        self, domain: "Domain", parameters: "Parameters", fractional_laplacian
    ):
        """
        Initialize validation methods.

        Physical Meaning:
            Sets up the validation methods with the computational domain,
            solver parameters, and fractional Laplacian operator.

        Args:
            domain (Domain): Computational domain with grid information.
            parameters (Parameters): Solver parameters.
            fractional_laplacian: Fractional Laplacian operator instance.
        """
        self.domain = domain
        self.parameters = parameters
        self._fractional_laplacian = fractional_laplacian
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"FFTSolverValidation initialized for domain {domain.shape}")

    def validate_solution(
        self, solution: np.ndarray, source: np.ndarray, tolerance: float = 1e-12
    ) -> Dict[str, Any]:
        """
        Validate solution to fractional Laplacian equation.

        Physical Meaning:
            Validates the solution by computing the residual of the equation
            L_β a = s and checking that it satisfies the equation within
            the specified tolerance.

        Mathematical Foundation:
            Computes residual: r = L_β a - s = μ(-Δ)^β a + λa - s
            and checks that ||r|| < tolerance.

        Args:
            solution (np.ndarray): Solution field a(x,φ,t).
            source (np.ndarray): Source field s(x,φ,t).
            tolerance (float): Tolerance for residual validation.

        Returns:
            Dict[str, Any]: Validation results including residual norm and status.
        """
        if solution.shape != self.domain.shape:
            raise ValueError(
                f"Solution shape {solution.shape} incompatible with domain {self.domain.shape}"
            )

        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain {self.domain.shape}"
            )

        # Compute residual
        residual = self._compute_residual(solution, source)

        # Compute residual norm
        residual_norm = np.linalg.norm(residual)
        source_norm = np.linalg.norm(source)
        relative_residual = (
            residual_norm / source_norm if source_norm > 0 else residual_norm
        )

        # Check validation status
        is_valid = relative_residual < tolerance

        validation_result = {
            "is_valid": is_valid,
            "residual_norm": residual_norm,
            "relative_residual": relative_residual,
            "tolerance": tolerance,
            "source_norm": source_norm,
        }

        if is_valid:
            self.logger.info(
                f"Solution validation passed: relative residual = {relative_residual:.2e}"
            )
        else:
            self.logger.warning(
                f"Solution validation failed: relative residual = {relative_residual:.2e} > {tolerance:.2e}"
            )

        return validation_result

    def _compute_residual(self, solution: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute residual r = L_β a - s.

        Physical Meaning:
            Computes the residual of the fractional Laplacian equation
            to validate the solution quality.

        Mathematical Foundation:
            Residual: r = L_β a - s = μ(-Δ)^β a + λa - s

        Args:
            solution (np.ndarray): Solution field a(x,φ,t).
            source (np.ndarray): Source field s(x,φ,t).

        Returns:
            np.ndarray: Residual field r(x,φ,t).
        """
        # Apply fractional Laplacian to solution
        laplacian_solution = self._fractional_laplacian.apply(solution)

        # Compute residual
        residual = (
            self.parameters.mu * laplacian_solution
            + self.parameters.lambda_param * solution
            - source
        )

        return residual

    def check_energy_conservation(
        self,
        field: np.ndarray,
        expected_energy: Optional[float] = None,
        tolerance: float = 1e-10,
    ) -> Dict[str, Any]:
        """
        Check energy conservation for field.

        Physical Meaning:
            Checks energy conservation by computing the total energy
            of the field and comparing with expected value.

        Mathematical Foundation:
            Energy: E = ∫ |a(x,φ,t)|² dV
            where dV is the 7D volume element.

        Args:
            field (np.ndarray): Field to check.
            expected_energy (Optional[float]): Expected energy value.
            tolerance (float): Tolerance for energy comparison.

        Returns:
            Dict[str, Any]: Energy conservation results.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        # Compute total energy
        energy_density = np.abs(field) ** 2
        total_energy = np.sum(energy_density)

        # Compute volume element
        dx = self.domain.L / self.domain.N
        dphi = 2 * np.pi / self.domain.N_phi
        dt = self.domain.T / self.domain.N_t
        volume_element = (dx**3) * (dphi**3) * dt

        # Scale by volume element
        total_energy *= volume_element

        result = {
            "total_energy": total_energy,
            "energy_density_max": np.max(energy_density),
            "energy_density_mean": np.mean(energy_density),
        }

        if expected_energy is not None:
            energy_error = abs(total_energy - expected_energy)
            relative_error = (
                energy_error / abs(expected_energy)
                if expected_energy != 0
                else energy_error
            )
            result.update(
                {
                    "expected_energy": expected_energy,
                    "energy_error": energy_error,
                    "relative_error": relative_error,
                    "is_conserved": relative_error < tolerance,
                }
            )

            if result["is_conserved"]:
                self.logger.info(
                    f"Energy conservation passed: relative error = {relative_error:.2e}"
                )
            else:
                self.logger.warning(
                    f"Energy conservation failed: relative error = {relative_error:.2e} > {tolerance:.2e}"
                )

        return result

    def check_boundary_conditions(
        self, field: np.ndarray, boundary_type: str = "periodic"
    ) -> Dict[str, Any]:
        """
        Check boundary conditions for field.

        Physical Meaning:
            Checks that the field satisfies the specified boundary conditions,
            which are crucial for the correctness of the solution.

        Args:
            field (np.ndarray): Field to check.
            boundary_type (str): Type of boundary conditions ('periodic', 'dirichlet', 'neumann').

        Returns:
            Dict[str, Any]: Boundary condition validation results.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        result = {"boundary_type": boundary_type, "is_satisfied": True, "errors": []}

        if boundary_type == "periodic":
            # Check periodicity in spatial dimensions
            for i in range(3):
                # Check periodicity along dimension i
                if i == 0:  # x dimension
                    left_boundary = field[0, :, :, :, :, :, :]
                    right_boundary = field[-1, :, :, :, :, :, :]
                elif i == 1:  # y dimension
                    left_boundary = field[:, 0, :, :, :, :, :]
                    right_boundary = field[:, -1, :, :, :, :, :]
                elif i == 2:  # z dimension
                    left_boundary = field[:, :, 0, :, :, :, :]
                    right_boundary = field[:, :, -1, :, :, :, :]

                boundary_error = np.linalg.norm(left_boundary - right_boundary)
                if boundary_error > 1e-12:
                    result["is_satisfied"] = False
                    result["errors"].append(
                        f"Periodicity violation in dimension {i}: error = {boundary_error:.2e}"
                    )

            # Check periodicity in phase dimensions
            for i in range(3):
                phase_dim = i + 3  # Phase dimensions are 3, 4, 5
                if phase_dim == 3:  # φ₁ dimension
                    left_boundary = field[:, :, :, 0, :, :, :]
                    right_boundary = field[:, :, :, -1, :, :, :]
                elif phase_dim == 4:  # φ₂ dimension
                    left_boundary = field[:, :, :, :, 0, :, :]
                    right_boundary = field[:, :, :, :, -1, :, :]
                elif phase_dim == 5:  # φ₃ dimension
                    left_boundary = field[:, :, :, :, :, 0, :]
                    right_boundary = field[:, :, :, :, :, -1, :]

                boundary_error = np.linalg.norm(left_boundary - right_boundary)
                if boundary_error > 1e-12:
                    result["is_satisfied"] = False
                    result["errors"].append(
                        f"Periodicity violation in phase dimension {i}: error = {boundary_error:.2e}"
                    )

        elif boundary_type == "dirichlet":
            # Check that field is zero at boundaries
            boundary_error = np.linalg.norm(
                field[0, :, :, :, :, :, :]
            ) + np.linalg.norm(field[-1, :, :, :, :, :, :])
            if boundary_error > 1e-12:
                result["is_satisfied"] = False
                result["errors"].append(
                    f"Dirichlet boundary condition violation: error = {boundary_error:.2e}"
                )

        if result["is_satisfied"]:
            self.logger.info(
                f"Boundary conditions satisfied for {boundary_type} boundaries"
            )
        else:
            self.logger.warning(
                f"Boundary conditions violated for {boundary_type} boundaries: {result['errors']}"
            )

        return result
