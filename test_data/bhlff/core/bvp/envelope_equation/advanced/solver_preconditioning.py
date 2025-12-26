"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Preconditioning for 7D BVP envelope equation solver.

This module implements preconditioning functionality
for the 7D BVP envelope equation solver.
"""

import numpy as np
from typing import Dict, Any, Tuple
from scipy.sparse import csc_matrix, diags

from ....domain.domain_7d import Domain7D


class SolverPreconditioning:
    """
    Preconditioning for 7D BVP envelope equation solver.

    Physical Meaning:
        Implements preconditioning techniques to improve the conditioning
        of the linear system for better convergence.
    """

    def __init__(self, domain: Domain7D, config: Dict[str, Any]):
        """Initialize preconditioning."""
        self.domain = domain
        self.config = config
        self.preconditioning_type = config.get("preconditioning_type", "jacobi")

    def apply_preconditioning(
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
        # Compute preconditioner
        preconditioner = self.compute_preconditioner(jacobian)

        # Apply preconditioning
        preconditioned_jacobian = preconditioner @ jacobian
        preconditioned_residual = preconditioner @ residual.flatten()

        return preconditioned_jacobian, preconditioned_residual.reshape(residual.shape)

    def compute_preconditioner(self, jacobian: csc_matrix) -> csc_matrix:
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
        if self.preconditioning_type == "jacobi":
            return self._compute_jacobi_preconditioner(jacobian)
        elif self.preconditioning_type == "ilu":
            return self._compute_ilu_preconditioner(jacobian)
        else:
            return self._compute_jacobi_preconditioner(jacobian)

    def _compute_jacobi_preconditioner(self, jacobian: csc_matrix) -> csc_matrix:
        """Compute Jacobi preconditioner."""
        # Extract diagonal
        diagonal = jacobian.diagonal()

        # Avoid division by zero
        diagonal = np.where(np.abs(diagonal) > 1e-12, diagonal, 1.0)

        # Create Jacobi preconditioner
        preconditioner = diags(1.0 / diagonal)
        return preconditioner

    def _compute_ilu_preconditioner(self, jacobian: csc_matrix) -> csc_matrix:
        """Compute ILU preconditioner (simplified)."""
        # Simplified ILU preconditioner (just Jacobi for now)
        return self._compute_jacobi_preconditioner(jacobian)
