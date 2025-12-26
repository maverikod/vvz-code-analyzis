"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP linear solver for 7D envelope equation.

This module implements linear solving functionality
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


class BVPLinearSolver:
    """
    BVP linear solver for 7D envelope equation.

    Physical Meaning:
        Provides linear solving functionality for BVP solving
        in the 7D envelope equation.
    """

    def __init__(
        self,
        domain: "Domain7DBVP",
        parameters: "Parameters7DBVP",
        derivatives: "SpectralDerivatives",
    ):
        """Initialize BVP linear solver."""
        self.domain = domain
        self.parameters = parameters
        self.derivatives = derivatives
        self.logger = logging.getLogger(__name__)

    def solve_linear_system(
        self, jacobian: np.ndarray, residual: np.ndarray
    ) -> np.ndarray:
        """
        Solve linear system for Newton-Raphson update.

        Physical Meaning:
            Solves the linear system J·δa = -r for the Newton-Raphson update,
            where J is the Jacobian and r is the residual.

        Args:
            jacobian (np.ndarray): Jacobian matrix.
            residual (np.ndarray): Residual vector.

        Returns:
            np.ndarray: Solution update vector.
        """
        self.logger.info("Solving BVP linear system")

        # Solve linear system
        try:
            update = np.linalg.solve(jacobian, -residual.flatten())
            update = update.reshape(residual.shape)
        except np.linalg.LinAlgError:
            # Fallback to least squares if system is singular
            self.logger.warning("Linear system is singular, using least squares")
            update = np.linalg.lstsq(jacobian, -residual.flatten(), rcond=None)[0]
            update = update.reshape(residual.shape)

        self.logger.info("BVP linear system solving completed")
        return update
