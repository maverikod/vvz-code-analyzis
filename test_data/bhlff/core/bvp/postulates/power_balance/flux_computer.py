"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Flux computation for Power Balance Postulate.

This module implements flux computation methods for the Power Balance
Postulate, including BVP flux calculation and boundary flux analysis.

Theoretical Background:
    BVP flux at external boundary represents energy flow across boundaries
    from amplitude gradients. This is a key component of power balance
    analysis in the BVP framework.

Example:
    >>> flux_computer = FluxComputer(domain, constants)
    >>> bvp_flux = flux_computer.compute_bvp_flux(envelope)
"""

import numpy as np
from typing import Dict, Any

from ....domain.domain import Domain
from ...bvp_constants import BVPConstants


class FluxComputer:
    """
    Flux computation for Power Balance Postulate.

    Physical Meaning:
        Computes BVP flux at external boundaries from amplitude gradients,
        representing energy flow across boundaries in the BVP system.

    Mathematical Foundation:
        Flux is proportional to gradient at boundary:
        Flux = ∇A · n̂ at boundary where n̂ is the normal vector.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize flux computer.

        Physical Meaning:
            Sets up the flux computer with domain and constants
            for boundary flux calculations.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants

    def compute_bvp_flux(self, envelope: np.ndarray) -> float:
        """
        Compute BVP flux at external boundary.

        Physical Meaning:
            Calculates energy flux across external boundaries
            from amplitude gradients.

        Mathematical Foundation:
            Flux is proportional to gradient at boundary:
            Flux = ∇A · n̂ at boundary where n̂ is the normal vector.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: BVP flux at boundary.
        """
        amplitude = np.abs(envelope)
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)

        # Flux is proportional to gradient at boundary
        boundary_flux = np.mean(np.abs(gradient[0, ...])) + np.mean(
            np.abs(gradient[-1, ...])
        )
        boundary_flux += np.mean(np.abs(gradient[:, 0, ...])) + np.mean(
            np.abs(gradient[:, -1, ...])
        )
        boundary_flux += np.mean(np.abs(gradient[:, :, 0, ...])) + np.mean(
            np.abs(gradient[:, :, -1, ...])
        )

        return boundary_flux / 6.0  # Average over 6 faces

    def compute_boundary_gradients(self, envelope: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compute gradients at all boundaries.

        Physical Meaning:
            Computes gradient components at all boundary faces
            for detailed flux analysis.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, np.ndarray]: Boundary gradients for each face.
        """
        amplitude = np.abs(envelope)
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)

        boundary_gradients = {
            "x_min": gradient[0, ...],
            "x_max": gradient[-1, ...],
            "y_min": gradient[:, 0, ...],
            "y_max": gradient[:, -1, ...],
            "z_min": gradient[:, :, 0, ...],
            "z_max": gradient[:, :, -1, ...],
        }

        return boundary_gradients
