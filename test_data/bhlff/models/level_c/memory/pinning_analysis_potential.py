"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pinning analysis potential module.

This module implements pinning potential functionality for pinning analysis
in Level C test C3 of 7D phase field theory.

Physical Meaning:
    Creates and manages pinning potentials for quench memory systems
    to analyze field stabilization and drift suppression.

Example:
    >>> potential_creator = PinningPotentialCreator(bvp_core)
    >>> potential = potential_creator.create_pinning_potential(domain, pinning_params)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore


class PinningPotentialCreator:
    """
    Pinning potential creator for quench memory systems.

    Physical Meaning:
        Creates and manages pinning potentials for quench memory systems
        to analyze field stabilization and drift suppression.

    Mathematical Foundation:
        Implements pinning potential creation:
        - Pinning potential: V_pin(x) = V₀ exp(-|x-x₀|²/σ²)
        - Pinning force: F_pin = -∇V_pin
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize pinning potential creator.

        Physical Meaning:
            Sets up the pinning potential creation system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def create_pinning_potential(
        self, domain: Dict[str, Any], pinning_params: Dict[str, Any]
    ) -> np.ndarray:
        """
        Create pinning potential.

        Physical Meaning:
            Creates pinning potential for quench memory analysis
            to analyze field stabilization and drift suppression.

        Mathematical Foundation:
            Creates pinning potential of the form:
            V_pin(x) = V₀ exp(-|x-x₀|²/σ²)

        Args:
            domain (Dict[str, Any]): Domain parameters.
            pinning_params (Dict[str, Any]): Pinning parameters.

        Returns:
            np.ndarray: Pinning potential field.
        """
        self.logger.info("Creating pinning potential")

        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Extract pinning parameters
        pinning_strength = pinning_params.get("pinning_strength", 1.0)
        pinning_center = pinning_params.get("pinning_center", [L / 2, L / 2, L / 2])
        pinning_width = pinning_params.get("pinning_width", L / 4)

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create pinning potential using step resonator function
        pinning_potential = pinning_strength * self._step_resonator_potential(
            X, Y, Z, pinning_center, pinning_width
        )

        self.logger.info("Pinning potential created")
        return pinning_potential

    def _step_resonator_potential(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        Z: np.ndarray,
        center: List[float],
        width: float,
    ) -> np.ndarray:
        """
        Create step resonator potential.

        Physical Meaning:
            Creates step resonator potential instead of exponential
            for 7D BVP theory compliance.

        Mathematical Foundation:
            V_step(x) = V₀ * Θ(r_cutoff - |x-x₀|)
            where Θ is step function and r_cutoff is cutoff radius.

        Args:
            X, Y, Z: Coordinate arrays
            center: Potential center coordinates
            width: Potential width parameter

        Returns:
            Step resonator potential field
        """
        # Compute distance from center
        distance_squared = (
            (X - center[0]) ** 2 + (Y - center[1]) ** 2 + (Z - center[2]) ** 2
        )

        # Step function: 1 inside cutoff, 0 outside
        cutoff_radius = width * np.sqrt(2)  # Match exponential width
        step_potential = np.where(distance_squared < cutoff_radius**2, 1.0, 0.0)

        return step_potential
