"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Potential analysis landscape module.

This module implements potential landscape analysis functionality for multi-particle systems
in Level F of 7D phase field theory.

Physical Meaning:
    Analyzes potential landscape including extrema, barriers, and wells
    for multi-particle systems.

Example:
    >>> landscape_analyzer = PotentialLandscapeAnalyzer(domain, particles, system_params)
    >>> landscape = landscape_analyzer.analyze_potential_landscape(potential)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import Particle, SystemParameters


class PotentialLandscapeAnalyzer:
    """
    Potential landscape analyzer for multi-particle systems.

    Physical Meaning:
        Analyzes potential landscape including extrema, barriers, and wells
        for multi-particle systems.

    Mathematical Foundation:
        Implements potential landscape analysis:
        - Extrema analysis: finding critical points
        - Barrier analysis: analyzing potential barriers
        - Well analysis: analyzing potential wells
    """

    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize potential landscape analyzer.

        Physical Meaning:
            Sets up the potential landscape analysis system with
            domain, particles, and system parameters.

        Args:
            domain: Domain parameters.
            particles (List[Particle]): List of particles.
            system_params (SystemParameters): System parameters.
        """
        self.domain = domain
        self.particles = particles
        self.system_params = system_params
        self.logger = logging.getLogger(__name__)

    def analyze_potential_landscape(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Analyze potential landscape.

        Physical Meaning:
            Analyzes potential landscape including extrema, barriers, and wells
            for multi-particle system.

        Mathematical Foundation:
            Analyzes potential landscape through:
            - Extrema analysis: finding critical points
            - Barrier analysis: analyzing potential barriers
            - Well analysis: analyzing potential wells

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Potential landscape analysis results.
        """
        self.logger.info("Analyzing potential landscape")

        # Find potential extrema
        extrema_analysis = self._find_potential_extrema(potential)

        # Analyze potential barriers
        barrier_analysis = self._analyze_potential_barriers(potential)

        # Analyze potential wells
        well_analysis = self._analyze_potential_wells(potential)

        results = {
            "extrema_analysis": extrema_analysis,
            "barrier_analysis": barrier_analysis,
            "well_analysis": well_analysis,
            "landscape_analysis_complete": True,
        }

        self.logger.info("Potential landscape analyzed")
        return results

    def _find_potential_extrema(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Find potential extrema.

        Physical Meaning:
            Finds extrema (minima and maxima) in potential landscape
            for multi-particle system.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Extrema analysis results.
        """
        # Find local minima
        local_minima = self._find_local_minima(potential)

        # Find local maxima
        local_maxima = self._find_local_maxima(potential)

        # Find global extrema
        global_minimum = np.min(potential)
        global_maximum = np.max(potential)

        # Calculate extrema statistics
        extrema_statistics = {
            "num_local_minima": len(local_minima),
            "num_local_maxima": len(local_maxima),
            "global_minimum": global_minimum,
            "global_maximum": global_maximum,
            "potential_range": global_maximum - global_minimum,
        }

        return {
            "local_minima": local_minima,
            "local_maxima": local_maxima,
            "global_minimum": global_minimum,
            "global_maximum": global_maximum,
            "extrema_statistics": extrema_statistics,
        }

    def _find_local_minima(self, potential: np.ndarray) -> List[Tuple[int, int, int]]:
        """
        Find local minima.

        Physical Meaning:
            Finds local minima in potential landscape
            using gradient analysis.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            List[Tuple[int, int, int]]: Local minima coordinates.
        """
        # Simplified local minima finding
        # In practice, this would involve proper gradient analysis
        local_minima = []

        # Find minima using simple comparison
        for i in range(1, potential.shape[0] - 1):
            for j in range(1, potential.shape[1] - 1):
                for k in range(1, potential.shape[2] - 1):
                    if self._is_local_minimum(potential, i, j, k):
                        local_minima.append((i, j, k))

        return local_minima

    def _find_local_maxima(self, potential: np.ndarray) -> List[Tuple[int, int, int]]:
        """
        Find local maxima.

        Physical Meaning:
            Finds local maxima in potential landscape
            using gradient analysis.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            List[Tuple[int, int, int]]: Local maxima coordinates.
        """
        # Simplified local maxima finding
        # In practice, this would involve proper gradient analysis
        local_maxima = []

        # Find maxima using simple comparison
        for i in range(1, potential.shape[0] - 1):
            for j in range(1, potential.shape[1] - 1):
                for k in range(1, potential.shape[2] - 1):
                    if self._is_local_maximum(potential, i, j, k):
                        local_maxima.append((i, j, k))

        return local_maxima

    def _is_local_minimum(self, potential: np.ndarray, i: int, j: int, k: int) -> bool:
        """
        Check if point is local minimum.

        Physical Meaning:
            Checks if point is local minimum in potential landscape
            by comparing with neighboring points.

        Args:
            potential (np.ndarray): Potential field.
            i (int): x coordinate.
            j (int): y coordinate.
            k (int): z coordinate.

        Returns:
            bool: True if point is local minimum.
        """
        # Check if point is local minimum
        center_value = potential[i, j, k]

        # Check all neighboring points
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                for dk in [-1, 0, 1]:
                    if di == 0 and dj == 0 and dk == 0:
                        continue

                    ni, nj, nk = i + di, j + dj, k + dk
                    if (
                        0 <= ni < potential.shape[0]
                        and 0 <= nj < potential.shape[1]
                        and 0 <= nk < potential.shape[2]
                    ):
                        if potential[ni, nj, nk] < center_value:
                            return False

        return True

    def _is_local_maximum(self, potential: np.ndarray, i: int, j: int, k: int) -> bool:
        """
        Check if point is local maximum.

        Physical Meaning:
            Checks if point is local maximum in potential landscape
            by comparing with neighboring points.

        Args:
            potential (np.ndarray): Potential field.
            i (int): x coordinate.
            j (int): y coordinate.
            k (int): z coordinate.

        Returns:
            bool: True if point is local maximum.
        """
        # Check if point is local maximum
        center_value = potential[i, j, k]

        # Check all neighboring points
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                for dk in [-1, 0, 1]:
                    if di == 0 and dj == 0 and dk == 0:
                        continue

                    ni, nj, nk = i + di, j + dj, k + dk
                    if (
                        0 <= ni < potential.shape[0]
                        and 0 <= nj < potential.shape[1]
                        and 0 <= nk < potential.shape[2]
                    ):
                        if potential[ni, nj, nk] > center_value:
                            return False

        return True

    def _analyze_potential_barriers(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Analyze potential barriers.

        Physical Meaning:
            Analyzes potential barriers in landscape
            for multi-particle system.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Barrier analysis results.
        """
        # Find potential barriers
        barriers = self._find_potential_barriers(potential)

        # Calculate barrier statistics
        barrier_statistics = {
            "num_barriers": len(barriers),
            "average_barrier_height": (
                np.mean([barrier["height"] for barrier in barriers])
                if barriers
                else 0.0
            ),
            "max_barrier_height": (
                max([barrier["height"] for barrier in barriers]) if barriers else 0.0
            ),
        }

        return {
            "barriers": barriers,
            "barrier_statistics": barrier_statistics,
        }

    def _find_potential_barriers(self, potential: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find potential barriers.

        Physical Meaning:
            Finds potential barriers in landscape
            using gradient analysis.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            List[Dict[str, Any]]: Potential barriers.
        """
        # Simplified barrier finding
        # In practice, this would involve proper barrier analysis
        barriers = []

        # Find barriers using simple analysis
        for i in range(1, potential.shape[0] - 1):
            for j in range(1, potential.shape[1] - 1):
                for k in range(1, potential.shape[2] - 1):
                    if self._is_potential_barrier(potential, i, j, k):
                        barrier = {
                            "position": (i, j, k),
                            "height": potential[i, j, k],
                            "type": "barrier",
                        }
                        barriers.append(barrier)

        return barriers

    def _is_potential_barrier(
        self, potential: np.ndarray, i: int, j: int, k: int
    ) -> bool:
        """
        Check if point is potential barrier.

        Physical Meaning:
            Checks if point is potential barrier in landscape
            by analyzing local curvature.

        Args:
            potential (np.ndarray): Potential field.
            i (int): x coordinate.
            j (int): y coordinate.
            k (int): z coordinate.

        Returns:
            bool: True if point is potential barrier.
        """
        # Simplified barrier detection
        # In practice, this would involve proper curvature analysis
        center_value = potential[i, j, k]

        # Check if point is higher than neighbors
        neighbor_values = []
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                for dk in [-1, 0, 1]:
                    if di == 0 and dj == 0 and dk == 0:
                        continue

                    ni, nj, nk = i + di, j + dj, k + dk
                    if (
                        0 <= ni < potential.shape[0]
                        and 0 <= nj < potential.shape[1]
                        and 0 <= nk < potential.shape[2]
                    ):
                        neighbor_values.append(potential[ni, nj, nk])

        # Check if center is higher than most neighbors
        if neighbor_values:
            return center_value > np.mean(neighbor_values) + np.std(neighbor_values)

        return False

    def _analyze_potential_wells(self, potential: np.ndarray) -> Dict[str, Any]:
        """
        Analyze potential wells.

        Physical Meaning:
            Analyzes potential wells in landscape
            for multi-particle system.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            Dict[str, Any]: Well analysis results.
        """
        # Find potential wells
        wells = self._find_potential_wells(potential)

        # Calculate well statistics
        well_statistics = {
            "num_wells": len(wells),
            "average_well_depth": (
                np.mean([well["depth"] for well in wells]) if wells else 0.0
            ),
            "max_well_depth": max([well["depth"] for well in wells]) if wells else 0.0,
        }

        return {
            "wells": wells,
            "well_statistics": well_statistics,
        }

    def _find_potential_wells(self, potential: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find potential wells.

        Physical Meaning:
            Finds potential wells in landscape
            using gradient analysis.

        Args:
            potential (np.ndarray): Potential field.

        Returns:
            List[Dict[str, Any]]: Potential wells.
        """
        # Simplified well finding
        # In practice, this would involve proper well analysis
        wells = []

        # Find wells using simple analysis
        for i in range(1, potential.shape[0] - 1):
            for j in range(1, potential.shape[1] - 1):
                for k in range(1, potential.shape[2] - 1):
                    if self._is_potential_well(potential, i, j, k):
                        well = {
                            "position": (i, j, k),
                            "depth": potential[i, j, k],
                            "type": "well",
                        }
                        wells.append(well)

        return wells

    def _is_potential_well(self, potential: np.ndarray, i: int, j: int, k: int) -> bool:
        """
        Check if point is potential well.

        Physical Meaning:
            Checks if point is potential well in landscape
            by analyzing local curvature.

        Args:
            potential (np.ndarray): Potential field.
            i (int): x coordinate.
            j (int): y coordinate.
            k (int): z coordinate.

        Returns:
            bool: True if point is potential well.
        """
        # Simplified well detection
        # In practice, this would involve proper curvature analysis
        center_value = potential[i, j, k]

        # Check if point is lower than neighbors
        neighbor_values = []
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                for dk in [-1, 0, 1]:
                    if di == 0 and dj == 0 and dk == 0:
                        continue

                    ni, nj, nk = i + di, j + dj, k + dk
                    if (
                        0 <= ni < potential.shape[0]
                        and 0 <= nj < potential.shape[1]
                        and 0 <= nk < potential.shape[2]
                    ):
                        neighbor_values.append(potential[ni, nj, nk])

        # Check if center is lower than most neighbors
        if neighbor_values:
            return center_value < np.mean(neighbor_values) - np.std(neighbor_values)

        return False
