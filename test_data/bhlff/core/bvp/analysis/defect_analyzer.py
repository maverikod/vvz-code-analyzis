"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological defect analyzer for BVP framework.

This module implements comprehensive analysis of topological defects
including identification, characterization, and interaction analysis.
"""

import numpy as np
from typing import Dict, Any, Tuple, List, Optional
from scipy.ndimage import label, center_of_mass

from ...domain import Domain
from ..bvp_constants import BVPConstants


class TopologicalDefectAnalyzer:
    """
    Analyzes topological defects in BVP fields.

    Physical Meaning:
        Identifies and analyzes topological defects in the BVP field
        to understand their properties and interactions.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any], constants: BVPConstants):
        """
        Initialize defect analyzer.

        Physical Meaning:
            Sets up defect analyzer with domain information and
            configuration parameters for comprehensive defect analysis.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Configuration parameters.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants

        # Analysis parameters
        self.defect_threshold = config.get("defect_threshold", 0.1)
        self.min_defect_size = config.get("min_defect_size", 5)
        self.defect_radius = config.get("defect_radius", 3)

    def analyze_block_defects(
        self, phase_block: np.ndarray, block_offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Analyze defects in a block of phase data.

        Physical Meaning:
            Identifies and analyzes topological defects in a block
            of phase data for efficient processing of large domains.

        Args:
            phase_block (np.ndarray): Phase data block.
            block_offset (int): Offset for block position.

        Returns:
            List[Dict[str, Any]]: List of defect information.
        """
        defects = []

        # Find potential defect locations
        defect_locations = self._find_defect_locations(phase_block)

        # Analyze each defect
        for location in defect_locations:
            # Adjust location for block offset
            adjusted_location = tuple(l + block_offset for l in location)

            # Analyze defect properties
            defect_info = self._analyze_defect_properties(phase_block, location)
            defect_info["location"] = adjusted_location
            defect_info["block_offset"] = block_offset

            defects.append(defect_info)

        return defects

    def analyze_defects(
        self, defects: List[Dict[str, Any]], charge_locations: List[Tuple[int, ...]]
    ) -> Dict[str, Any]:
        """
        Analyze collected defects and their interactions.

        Physical Meaning:
            Performs comprehensive analysis of all identified defects
            including their properties, interactions, and collective behavior.

        Args:
            defects (List[Dict[str, Any]]): List of defect information.
            charge_locations (List[Tuple[int, ...]]): Charge locations.

        Returns:
            Dict[str, Any]: Comprehensive defect analysis.
        """
        if not defects:
            return {
                "defect_count": 0,
                "defect_types": [],
                "defect_strengths": [],
                "defect_interactions": [],
                "total_positive_charge": 0.0,
                "total_negative_charge": 0.0,
            }

        # Analyze defect types
        defect_types = [defect["type"] for defect in defects]
        defect_strengths = [defect["strength"] for defect in defects]

        # Analyze defect interactions
        defect_interactions = self._analyze_defect_interactions(defects)

        # Compute total charges
        total_positive = sum(
            defect["strength"] for defect in defects if defect["strength"] > 0
        )
        total_negative = sum(
            defect["strength"] for defect in defects if defect["strength"] < 0
        )

        # Analyze defect distribution
        distribution_analysis = self._analyze_defect_distribution(defects)

        return {
            "defect_count": len(defects),
            "defect_types": defect_types,
            "defect_strengths": defect_strengths,
            "defect_interactions": defect_interactions,
            "total_positive_charge": float(total_positive),
            "total_negative_charge": float(total_negative),
            "distribution_analysis": distribution_analysis,
        }

    def _find_defect_locations(self, phase: np.ndarray) -> List[Tuple[int, ...]]:
        """Find potential defect locations in phase field."""
        # Compute phase gradients
        gradients = []
        for axis in range(phase.ndim):
            grad = np.gradient(phase, axis=axis)
            gradients.append(grad)

        # Compute gradient magnitude
        grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients))

        # Find high gradient regions (potential defects)
        high_grad_threshold = np.mean(grad_magnitude) + 2 * np.std(grad_magnitude)
        high_grad_regions = grad_magnitude > high_grad_threshold

        # Use connected component analysis to find defect regions
        labeled_regions, num_regions = label(high_grad_regions)

        # Find center of mass for each region
        defect_locations = []
        for region_id in range(1, num_regions + 1):
            region_mask = labeled_regions == region_id

            # Check if region is large enough
            if np.sum(region_mask) >= self.min_defect_size:
                # Find center of mass
                center = center_of_mass(region_mask)
                defect_locations.append(tuple(int(c) for c in center))

        return defect_locations

    def _analyze_defect_properties(
        self, phase: np.ndarray, location: Tuple[int, ...]
    ) -> Dict[str, Any]:
        """Analyze properties of a specific defect."""
        # Extract defect region
        defect_region = self._extract_defect_region(phase, location)

        # Compute defect strength
        strength = self._compute_defect_strength(defect_region)

        # Determine defect type
        defect_type = self._classify_defect_type(strength)

        # Compute defect size
        size = self._compute_defect_size(defect_region)

        # Compute defect stability
        stability = self._compute_defect_stability(defect_region)

        return {
            "type": defect_type,
            "strength": float(strength),
            "size": int(size),
            "stability": float(stability),
            "region": defect_region,
        }

    def _extract_defect_region(
        self, phase: np.ndarray, location: Tuple[int, ...]
    ) -> np.ndarray:
        """Extract region around defect location."""
        # Define extraction bounds
        bounds = []
        for i, coord in enumerate(location):
            start = max(0, coord - self.defect_radius)
            end = min(phase.shape[i], coord + self.defect_radius + 1)
            bounds.append(slice(start, end))

        # Extract region
        return phase[tuple(bounds)]

    def _compute_defect_strength(self, defect_region: np.ndarray) -> float:
        """Compute strength of topological defect."""
        # Compute phase gradients in region
        gradients = []
        for axis in range(defect_region.ndim):
            grad = np.gradient(defect_region, axis=axis)
            gradients.append(grad)

        # Compute gradient magnitude
        grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients))

        # Defect strength is related to gradient magnitude
        strength = np.mean(grad_magnitude)

        return float(strength)

    def _classify_defect_type(self, strength: float) -> str:
        """Classify defect type based on strength."""
        if strength > 2 * self.defect_threshold:
            return "strong"
        elif strength > self.defect_threshold:
            return "medium"
        else:
            return "weak"

    def _compute_defect_size(self, defect_region: np.ndarray) -> int:
        """Compute size of defect region."""
        return defect_region.size

    def _compute_defect_stability(self, defect_region: np.ndarray) -> float:
        """Compute stability of defect."""
        # Compute phase variance in region
        phase_variance = np.var(defect_region)

        # Stability is inverse of variance
        stability = 1.0 / (1.0 + phase_variance)

        return float(stability)

    def _analyze_defect_interactions(
        self, defects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze interactions between defects."""
        interactions = []

        for i, defect1 in enumerate(defects):
            for j, defect2 in enumerate(defects):
                if i != j:
                    # Calculate distance between defects
                    loc1 = defect1["location"]
                    loc2 = defect2["location"]
                    distance = np.sqrt(sum((a - b) ** 2 for a, b in zip(loc1, loc2)))

                    # Calculate interaction strength
                    strength1 = defect1["strength"]
                    strength2 = defect2["strength"]
                    interaction_strength = (strength1 * strength2) / (
                        distance**2 + 1e-10
                    )

                    # Determine interaction type
                    if strength1 * strength2 > 0:
                        interaction_type = "repulsive"
                    else:
                        interaction_type = "attractive"

                    interaction = {
                        "defect_pair": (i, j),
                        "distance": float(distance),
                        "interaction_strength": float(interaction_strength),
                        "interaction_type": interaction_type,
                    }
                    interactions.append(interaction)

        return interactions

    def _analyze_defect_distribution(
        self, defects: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze spatial distribution of defects."""
        if not defects:
            return {
                "spatial_clustering": 0.0,
                "defect_density": 0.0,
                "distribution_uniformity": 0.0,
            }

        # Extract defect locations
        locations = [defect["location"] for defect in defects]

        # Compute spatial clustering
        clustering = self._compute_spatial_clustering(locations)

        # Compute defect density
        total_volume = np.prod(self.domain.shape)
        defect_density = len(defects) / total_volume

        # Compute distribution uniformity
        uniformity = self._compute_distribution_uniformity(locations)

        return {
            "spatial_clustering": float(clustering),
            "defect_density": float(defect_density),
            "distribution_uniformity": float(uniformity),
        }

    def _compute_spatial_clustering(self, locations: List[Tuple[int, ...]]) -> float:
        """Compute spatial clustering of defects."""
        if len(locations) < 2:
            return 0.0

        # Compute pairwise distances
        distances = []
        for i, loc1 in enumerate(locations):
            for j, loc2 in enumerate(locations):
                if i != j:
                    distance = np.sqrt(sum((a - b) ** 2 for a, b in zip(loc1, loc2)))
                    distances.append(distance)

        # Clustering is inverse of average distance
        avg_distance = np.mean(distances)
        clustering = 1.0 / (1.0 + avg_distance)

        return float(clustering)

    def _compute_distribution_uniformity(
        self, locations: List[Tuple[int, ...]]
    ) -> float:
        """Compute uniformity of defect distribution."""
        if len(locations) < 2:
            return 1.0

        # Compute variance in each dimension
        variances = []
        for dim in range(len(locations[0])):
            coords = [loc[dim] for loc in locations]
            variances.append(np.var(coords))

        # Uniformity is inverse of total variance
        total_variance = np.sum(variances)
        uniformity = 1.0 / (1.0 + total_variance)

        return float(uniformity)
