"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quenches analyzer implementation for BVP framework.

This module implements the analysis functionality for quench events in the BVP field,
computing detailed properties and energy dissipation characteristics.

Physical Meaning:
    Analyzes quench events to compute detailed properties including size, shape,
    amplitude characteristics, and energy dissipation patterns.

Mathematical Foundation:
    Uses statistical analysis and energy calculations to quantify quench properties
    and validate energy dump events in the BVP field.

Example:
    >>> analyzer = QuenchesAnalyzer(domain, constants)
    >>> properties = analyzer.analyze_quench_properties(envelope, quench_detection)
"""

import numpy as np
from typing import Dict, Any

from ..domain.domain import Domain
from .bvp_constants import BVPConstants


class QuenchesAnalyzer:
    """
    Analyzer for quench events in BVP field.

    Physical Meaning:
        Computes detailed properties of quench events including
        size, amplitude characteristics, and energy dissipation.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize quenches analyzer.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.energy_dump_threshold = constants.get_quench_parameter(
            "energy_dump_threshold"
        )

    def analyze_quench_properties(
        self, envelope: np.ndarray, quench_detection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze properties of detected quenches.

        Physical Meaning:
            Computes detailed properties of quench events
            including size, shape, and amplitude characteristics.

        Args:
            envelope (np.ndarray): BVP envelope.
            quench_detection (Dict[str, Any]): Quench detection results.

        Returns:
            Dict[str, Any]: Quench properties analysis.
        """
        amplitude = np.abs(envelope)
        quench_mask = quench_detection["quench_mask"]
        quench_locations = quench_detection["quench_locations"]

        # Analyze individual quenches
        quench_properties = []
        for i, location in enumerate(quench_locations):
            properties = self._analyze_individual_quench(
                amplitude, quench_mask, location, i
            )
            quench_properties.append(properties)

        # Compute overall quench statistics
        if quench_properties:
            avg_quench_size = np.mean([q["size"] for q in quench_properties])
            avg_quench_amplitude = np.mean(
                [q["min_amplitude"] for q in quench_properties]
            )
            avg_quench_depth = np.mean([q["depth"] for q in quench_properties])
        else:
            avg_quench_size = 0
            avg_quench_amplitude = 0
            avg_quench_depth = 0

        return {
            "individual_quenches": quench_properties,
            "avg_quench_size": avg_quench_size,
            "avg_quench_amplitude": avg_quench_amplitude,
            "avg_quench_depth": avg_quench_depth,
        }

    def analyze_energy_dumps(
        self, envelope: np.ndarray, quench_detection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze energy dumps at quench locations.

        Physical Meaning:
            Computes energy dissipation at quench locations
            to quantify energy dump events.

        Args:
            envelope (np.ndarray): BVP envelope.
            quench_detection (Dict[str, Any]): Quench detection results.

        Returns:
            Dict[str, Any]: Energy dump analysis.
        """
        amplitude = np.abs(envelope)
        quench_mask = quench_detection["quench_mask"]

        # Compute energy in quench regions
        quench_energy = amplitude[quench_mask] ** 2
        total_quench_energy = np.sum(quench_energy)

        # Compute energy dump rate
        energy_dump_rate = total_quench_energy / (
            amplitude.size * np.mean(amplitude**2)
        )

        # Check if energy dumps are significant
        significant_dumps = energy_dump_rate > self.energy_dump_threshold

        return {
            "total_quench_energy": total_quench_energy,
            "energy_dump_rate": energy_dump_rate,
            "energy_dump_ratio": energy_dump_rate,
            "significant_dumps": significant_dumps,
        }

    def _analyze_individual_quench(
        self,
        amplitude: np.ndarray,
        quench_mask: np.ndarray,
        location: tuple,
        quench_id: int,
    ) -> Dict[str, Any]:
        """
        Analyze properties of individual quench.

        Physical Meaning:
            Computes detailed properties of a single quench
            event including size, amplitude, and depth.

        Args:
            amplitude (np.ndarray): Field amplitude.
            quench_mask (np.ndarray): Binary quench mask.
            location (tuple): Quench center location.
            quench_id (int): Quench identifier.

        Returns:
            Dict[str, Any]: Individual quench properties.
        """
        # Find quench region around location
        quench_region = self._extract_quench_region(amplitude, quench_mask, location)

        # Compute quench properties
        quench_amplitude = amplitude[quench_region]
        min_amplitude = np.min(quench_amplitude)
        max_amplitude = np.max(quench_amplitude)
        mean_amplitude = np.mean(quench_amplitude)

        # Compute quench depth
        surrounding_amplitude = self._compute_surrounding_amplitude(amplitude, location)
        depth = surrounding_amplitude - min_amplitude

        # Compute quench size
        size = np.sum(quench_region)

        return {
            "id": quench_id,
            "location": location,
            "size": size,
            "min_amplitude": min_amplitude,
            "max_amplitude": max_amplitude,
            "mean_amplitude": mean_amplitude,
            "depth": depth,
        }

    def _extract_quench_region(
        self, amplitude: np.ndarray, quench_mask: np.ndarray, location: tuple
    ) -> np.ndarray:
        """
        Extract region around quench location.

        Physical Meaning:
            Creates mask for quench region around specified
            location for detailed analysis.

        Args:
            amplitude (np.ndarray): Field amplitude.
            quench_mask (np.ndarray): Binary quench mask.
            location (tuple): Quench center location.

        Returns:
            np.ndarray: Quench region mask.
        """
        # Create region mask around location
        region_size = 10  # Adjust based on domain size
        region_mask = np.zeros_like(amplitude, dtype=bool)

        # Define region bounds
        bounds = []
        for i, coord in enumerate(location):
            lower = max(0, int(coord - region_size))
            upper = min(amplitude.shape[i], int(coord + region_size))
            bounds.append((lower, upper))

        # Create region mask
        region_mask[
            bounds[0][0] : bounds[0][1],
            bounds[1][0] : bounds[1][1],
            bounds[2][0] : bounds[2][1],
        ] = True

        # Intersect with quench mask
        quench_region = region_mask & quench_mask

        return quench_region

    def _compute_surrounding_amplitude(
        self, amplitude: np.ndarray, location: tuple
    ) -> float:
        """
        Compute amplitude in surrounding region.

        Physical Meaning:
            Calculates average amplitude in region surrounding
            quench to determine quench depth.

        Args:
            amplitude (np.ndarray): Field amplitude.
            location (tuple): Quench center location.

        Returns:
            float: Surrounding amplitude.
        """
        # Define surrounding region
        region_size = 20  # Larger than quench region
        surrounding_amplitude = []

        # Sample surrounding region
        for i in range(-region_size, region_size + 1):
            for j in range(-region_size, region_size + 1):
                for k in range(-region_size, region_size + 1):
                    x = int(location[0] + i)
                    y = int(location[1] + j)
                    z = int(location[2] + k)

                    if (
                        0 <= x < amplitude.shape[0]
                        and 0 <= y < amplitude.shape[1]
                        and 0 <= z < amplitude.shape[2]
                    ):
                        surrounding_amplitude.append(amplitude[x, y, z])

        return np.mean(surrounding_amplitude) if surrounding_amplitude else 0
