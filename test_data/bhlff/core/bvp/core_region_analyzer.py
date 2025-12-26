"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core region analysis for BVP framework.

This module implements algorithms for identifying and analyzing the core region
of the BVP envelope, including center of mass calculation and radius determination.

Physical Meaning:
    Identifies the central region where envelope amplitude is highest
    and defines core boundaries based on amplitude decay patterns.

Mathematical Foundation:
    Uses center of mass calculation and amplitude threshold analysis
    to define the core region boundaries.

Example:
    >>> analyzer = CoreRegionAnalyzer(domain, constants)
    >>> core_region = analyzer.identify_core_region(envelope)
"""

import numpy as np
from typing import Dict, Any, List

from ..domain.domain import Domain
from .bvp_constants import BVPConstants


class CoreRegionAnalyzer:
    """
    Analyzer for core region identification and analysis.

    Physical Meaning:
        Identifies the central region where envelope amplitude is highest
        and defines core boundaries based on amplitude decay.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize core region analyzer.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.core_radius = constants.get_physical_parameter("core_radius")

    def identify_core_region(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Identify the core region of the envelope.

        Physical Meaning:
            Finds the central region where envelope amplitude is highest
            and defines core boundaries based on amplitude decay.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Core region parameters.
        """
        amplitude = np.abs(envelope)

        # Find center of mass
        center = self._find_center_of_mass(amplitude)

        # Define core radius based on amplitude decay
        core_radius = self._compute_core_radius(amplitude, center)

        # Create core mask
        core_mask = self._create_core_mask(amplitude, center, core_radius)

        return {
            "center": center,
            "radius": core_radius,
            "mask": core_mask,
            "volume": np.sum(core_mask),
        }

    def _find_center_of_mass(self, amplitude: np.ndarray) -> List[float]:
        """
        Find center of mass of the amplitude distribution.

        Physical Meaning:
            Computes center of mass as weighted average of coordinates
            with amplitude as weight.

        Args:
            amplitude (np.ndarray): Envelope amplitude.

        Returns:
            List[float]: Center of mass coordinates.
        """
        center = []
        for axis in range(amplitude.ndim):
            # Create coordinate array for this axis
            coord_array = np.arange(amplitude.shape[axis])
            # Reshape to match amplitude dimensions
            coord_array = coord_array.reshape(
                [1] * axis + [amplitude.shape[axis]] + [1] * (amplitude.ndim - axis - 1)
            )
            axis_center = np.sum(amplitude * coord_array) / np.sum(amplitude)
            center.append(axis_center)
        return center

    def _compute_core_radius(self, amplitude: np.ndarray, center: List[float]) -> float:
        """
        Compute effective core radius.

        Physical Meaning:
            Finds radius where amplitude drops to 1/e of maximum,
            defining effective core boundary.

        Args:
            amplitude (np.ndarray): Envelope amplitude.
            center (List[float]): Center coordinates.

        Returns:
            float: Effective core radius.
        """
        # Find radius where amplitude drops to 1/e of maximum
        max_amplitude = np.max(amplitude)
        threshold = max_amplitude / np.e

        # Find distance from center where amplitude drops below threshold
        distances = self._compute_distances_from_center(amplitude, center)
        low_amplitude_mask = amplitude < threshold
        if np.any(low_amplitude_mask):
            core_radius = np.min(distances[low_amplitude_mask])
        else:
            # If no points below threshold, use maximum distance
            core_radius = np.max(distances)

        return core_radius

    def _compute_distances_from_center(
        self, amplitude: np.ndarray, center: List[float]
    ) -> np.ndarray:
        """
        Compute distances from center for each point.

        Physical Meaning:
            Calculates Euclidean distance from center for each
            point in the domain.

        Args:
            amplitude (np.ndarray): Envelope amplitude.
            center (List[float]): Center coordinates.

        Returns:
            np.ndarray: Distance field.
        """
        # Create coordinate arrays
        coords = np.meshgrid(
            *[np.arange(amplitude.shape[i]) for i in range(amplitude.ndim)],
            indexing="ij",
        )

        # Compute distances
        distances = np.zeros_like(amplitude)
        for i, coord in enumerate(coords):
            distances += (coord - center[i]) ** 2
        distances = np.sqrt(distances)

        return distances

    def _create_core_mask(
        self, amplitude: np.ndarray, center: List[float], radius: float
    ) -> np.ndarray:
        """
        Create mask for core region.

        Physical Meaning:
            Creates binary mask identifying points within
            the core region boundary.

        Args:
            amplitude (np.ndarray): Envelope amplitude.
            center (List[float]): Center coordinates.
            radius (float): Core radius.

        Returns:
            np.ndarray: Core region mask.
        """
        distances = self._compute_distances_from_center(amplitude, center)
        core_mask = distances <= radius

        return core_mask
