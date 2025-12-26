"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pinned beating field creation module.

This module implements field creation functionality for pinned beating analysis
in Level C test C4 of 7D phase field theory.

Physical Meaning:
    Creates pinned dual-mode fields with pinning effects for analysis
    of mode beating with drift suppression.

Example:
    >>> field_creator = PinnedFieldCreator()
    >>> field = field_creator.create_pinned_dual_mode_field(domain, dual_mode, pinning_params)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .data_structures import DualModeSource


class PinnedFieldCreator:
    """
    Pinned field creation for Level C test C4.

    Physical Meaning:
        Creates pinned dual-mode fields with pinning effects for
        analysis of mode beating with drift suppression.

    Mathematical Foundation:
        Creates pinned dual-mode fields of the form:
        s(x,t) = s₁(x) e^(-iω₁t) + s₂(x) e^(-iω₂t) + p(x)
        where p(x) represents the pinning potential.
    """

    def __init__(self):
        """Initialize pinned field creator."""
        self.logger = logging.getLogger(__name__)

    def create_pinned_dual_mode_field(
        self,
        domain: Dict[str, Any],
        dual_mode: DualModeSource,
        pinning_params: Dict[str, Any],
    ) -> np.ndarray:
        """
        Create pinned dual-mode field.

        Physical Meaning:
            Creates a field configuration with dual-mode
            excitation and pinning effects.

        Mathematical Foundation:
            Creates a pinned dual-mode field of the form:
            s(x,t) = s₁(x) e^(-iω₁t) + s₂(x) e^(-iω₂t) + p(x)
            where p(x) represents the pinning potential.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            dual_mode (DualModeSource): Dual-mode source specification.
            pinning_params (Dict[str, Any]): Pinning parameters.

        Returns:
            np.ndarray: Pinned dual-mode field configuration.
        """
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create Gaussian profiles
        center = np.array([L / 2, L / 2, L / 2])
        sigma = L / 8

        # First mode profile using step resonator model
        profile_1 = self._step_resonator_mode_profile(X, Y, Z, center, sigma)

        # Second mode profile using step resonator model
        profile_2 = self._step_resonator_mode_profile(X - L / 4, Y, Z, center, sigma)

        # Create pinning potential
        pinning_potential = self._create_pinning_potential(domain, pinning_params)

        # Combine modes with pinning
        field_pinned = (
            dual_mode.amplitude_1 * profile_1
            + dual_mode.amplitude_2 * profile_2
            + pinning_potential
        )

        return field_pinned

    def _create_pinning_potential(
        self, domain: Dict[str, Any], pinning_params: Dict[str, Any]
    ) -> np.ndarray:
        """
        Create pinning potential.

        Physical Meaning:
            Creates a pinning potential that suppresses
            drift and modifies beating patterns.

        Mathematical Foundation:
            Creates a Gaussian pinning potential:
            p(x) = A exp(-|x - x₀|²/(2σ²))

        Args:
            domain (Dict[str, Any]): Domain parameters.
            pinning_params (Dict[str, Any]): Pinning parameters.

        Returns:
            np.ndarray: Pinning potential field.
        """
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create pinning potential
        pinning_strength = pinning_params.get("pinning_strength", 1.0)
        pinning_center = pinning_params.get("pinning_center", [L / 2, L / 2, L / 2])
        pinning_width = pinning_params.get("pinning_width", L / 4)

        pinning_potential = pinning_strength * self._step_resonator_pinning_potential(
            X, Y, Z, pinning_center, pinning_width
        )

        return pinning_potential

    def _step_resonator_pinning_potential(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        Z: np.ndarray,
        pinning_center: List[float],
        pinning_width: float,
    ) -> np.ndarray:
        """
        Step resonator pinning potential according to 7D BVP theory.

        Physical Meaning:
            Implements step function pinning potential instead of exponential decay
            according to 7D BVP theory principles.
        """
        distance_squared = (
            (X - pinning_center[0]) ** 2
            + (Y - pinning_center[1]) ** 2
            + (Z - pinning_center[2]) ** 2
        )
        cutoff_radius_squared = (pinning_width * 0.8) ** 2  # 80% of pinning width
        return np.where(distance_squared < cutoff_radius_squared, 1.0, 0.0)

    def _step_resonator_mode_profile(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        Z: np.ndarray,
        center: np.ndarray,
        sigma: float,
    ) -> np.ndarray:
        """
        Step resonator mode profile according to 7D BVP theory.

        Physical Meaning:
            Implements step function mode profile instead of exponential decay
            according to 7D BVP theory principles.
        """
        distance_squared = (
            (X - center[0]) ** 2 + (Y - center[1]) ** 2 + (Z - center[2]) ** 2
        )
        cutoff_radius_squared = (sigma * 2.0) ** 2  # 2-sigma cutoff
        return np.where(distance_squared < cutoff_radius_squared, 1.0, 0.0)
