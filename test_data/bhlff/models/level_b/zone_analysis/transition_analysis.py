"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transition analysis module for zone analysis.

This module implements transition region analysis operations for zone analysis,
including gradient analysis, phase field analysis, and topological analysis.

Physical Meaning:
    Performs complete transition region analysis using
    full 7D analysis including level set analysis,
    phase field methods, and topological analysis.

Mathematical Foundation:
    Implements full transition analysis:
    - Level set analysis for transition detection
    - Phase field method for boundary evolution
    - Topological analysis of transition regions
    - Energy landscape analysis
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class TransitionAnalysis:
    """
    Transition analysis for zone analysis.

    Physical Meaning:
        Performs complete transition region analysis using
        full 7D analysis including level set analysis,
        phase field methods, and topological analysis.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize transition analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def identify_transition_regions(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Identify transition regions using full 7D analysis.

        Physical Meaning:
            Identifies transition regions between different zones
            using complete 7D analysis including level set analysis,
            phase field methods, and topological analysis.
        """
        amplitude = np.abs(envelope)
        transition_regions = []

        # Use full boundary detection for transition region identification
        boundary_analysis = self.bvp_core.zone_analysis.identify_zone_boundaries(
            envelope
        )

        # Extract phase field boundaries for transition analysis
        phase_field_boundaries = boundary_analysis.get("phase_field_boundaries", {})

        # Extract topological boundaries for transition analysis
        topological_boundaries = boundary_analysis.get("topological_boundaries", {})

        # Extract energy landscape for transition analysis
        energy_landscape = boundary_analysis.get("energy_landscape", {})

        # Identify transition regions using multiple criteria
        transition_regions.extend(self._identify_gradient_transitions(amplitude))
        transition_regions.extend(
            self._identify_phase_field_transitions(phase_field_boundaries)
        )
        transition_regions.extend(
            self._identify_topological_transitions(topological_boundaries)
        )
        transition_regions.extend(self._identify_energy_transitions(energy_landscape))

        # Merge and filter transition regions
        transition_regions = self._merge_transition_regions(transition_regions)

        return transition_regions

    def _identify_gradient_transitions(
        self, amplitude: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Identify transition regions using gradient analysis."""
        transition_regions = []

        if amplitude.ndim >= 3:
            # Compute gradients in all dimensions
            gradients = {}
            for dim in range(amplitude.ndim):
                gradients[f"dim_{dim}"] = np.gradient(amplitude, axis=dim)

            # Compute gradient magnitude
            grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

            # Find high-gradient regions (potential transitions)
            threshold = np.mean(grad_magnitude) + 2 * np.std(grad_magnitude)
            transition_mask = grad_magnitude > threshold

            # Get transition region coordinates
            transition_coords = np.where(transition_mask)

            if len(transition_coords[0]) > 0:
                # Create transition region
                transition_region = {
                    "region_type": "gradient_transition",
                    "region_location": tuple(
                        transition_coords[dim][0]
                        for dim in range(len(transition_coords))
                    ),
                    "transition_strength": float(
                        np.mean(grad_magnitude[transition_mask])
                    ),
                    "detection_method": "gradient_analysis",
                }
                transition_regions.append(transition_region)

        return transition_regions

    def _identify_phase_field_transitions(
        self, phase_field_boundaries: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify transition regions using phase field analysis."""
        transition_regions = []

        if phase_field_boundaries:
            boundary_mask = phase_field_boundaries.get("boundary_mask")
            gradient_magnitude = phase_field_boundaries.get("gradient_magnitude")

            if boundary_mask is not None and gradient_magnitude is not None:
                # Find transition regions in phase field
                transition_coords = np.where(boundary_mask)

                if len(transition_coords[0]) > 0:
                    transition_region = {
                        "region_type": "phase_field_transition",
                        "region_location": tuple(
                            transition_coords[dim][0]
                            for dim in range(len(transition_coords))
                        ),
                        "transition_strength": float(
                            np.mean(gradient_magnitude[boundary_mask])
                        ),
                        "detection_method": "phase_field_analysis",
                    }
                    transition_regions.append(transition_region)

        return transition_regions

    def _identify_topological_transitions(
        self, topological_boundaries: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify transition regions using topological analysis."""
        transition_regions = []

        if topological_boundaries:
            critical_points = topological_boundaries.get("critical_points", [])

            for point in critical_points:
                if point.get("type") == "critical_point":
                    transition_region = {
                        "region_type": "topological_transition",
                        "region_location": point.get("coordinates"),
                        "transition_strength": float(
                            point.get("gradient_magnitude", 0.0)
                        ),
                        "detection_method": "topological_analysis",
                    }
                    transition_regions.append(transition_region)

        return transition_regions

    def _identify_energy_transitions(
        self, energy_landscape: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify transition regions using energy landscape analysis."""
        transition_regions = []

        if energy_landscape:
            transition_regions_data = energy_landscape.get("transition_regions", {})
            transition_mask = transition_regions_data.get("transition_mask")

            if transition_mask is not None:
                # Find transition regions in energy landscape
                transition_coords = np.where(transition_mask)

                if len(transition_coords[0]) > 0:
                    transition_region = {
                        "region_type": "energy_transition",
                        "region_location": tuple(
                            transition_coords[dim][0]
                            for dim in range(len(transition_coords))
                        ),
                        "transition_strength": float(
                            transition_regions_data.get("transition_density", 0.0)
                        ),
                        "detection_method": "energy_landscape_analysis",
                    }
                    transition_regions.append(transition_region)

        return transition_regions

    def _merge_transition_regions(
        self, transition_regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge and filter transition regions."""
        if not transition_regions:
            return []

        # Group regions by location (within some tolerance)
        merged_regions = []
        used_indices = set()

        for i, region in enumerate(transition_regions):
            if i in used_indices:
                continue

            # Find nearby regions to merge
            nearby_regions = [region]
            used_indices.add(i)

            for j, other_region in enumerate(transition_regions):
                if j in used_indices:
                    continue

                # Check if regions are nearby (within 5 units)
                if self._are_regions_nearby(region, other_region, tolerance=5):
                    nearby_regions.append(other_region)
                    used_indices.add(j)

            # Merge nearby regions
            merged_region = self._merge_nearby_regions(nearby_regions)
            merged_regions.append(merged_region)

        return merged_regions

    def _are_regions_nearby(
        self, region1: Dict[str, Any], region2: Dict[str, Any], tolerance: float
    ) -> bool:
        """Check if two regions are nearby."""
        loc1 = region1.get("region_location", (0, 0, 0))
        loc2 = region2.get("region_location", (0, 0, 0))

        # Compute distance between regions
        distance = np.sqrt(sum((a - b) ** 2 for a, b in zip(loc1, loc2)))

        return distance <= tolerance

    def _merge_nearby_regions(self, regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge nearby regions into a single region."""
        if len(regions) == 1:
            return regions[0]

        # Compute average location
        locations = [region.get("region_location", (0, 0, 0)) for region in regions]
        avg_location = tuple(
            np.mean([loc[dim] for loc in locations]) for dim in range(len(locations[0]))
        )

        # Compute average transition strength
        strengths = [region.get("transition_strength", 0.0) for region in regions]
        avg_strength = np.mean(strengths)

        # Combine detection methods
        methods = [region.get("detection_method", "unknown") for region in regions]
        combined_method = " + ".join(set(methods))

        return {
            "region_type": "merged_transition",
            "region_location": avg_location,
            "transition_strength": float(avg_strength),
            "detection_method": combined_method,
            "num_merged_regions": len(regions),
        }
