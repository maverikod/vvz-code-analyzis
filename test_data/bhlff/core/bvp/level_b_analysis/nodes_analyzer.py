"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spherical nodes analyzer for Level B BVP interface.

This module implements analysis of spherical standing nodes in the BVP
envelope for the Level B BVP interface, detecting the absence of
spherical standing wave nodes according to the theory.

Physical Meaning:
    Detects spherical standing wave nodes in the BVP envelope, which
    should be absent in the fundamental field configuration according
    to the 7D phase field theory in the pure fractional regime.

Mathematical Foundation:
    Analyzes local minima in the field amplitude to detect potential
    nodes and checks for spherical clustering patterns that would
    indicate standing wave behavior.

Example:
    >>> analyzer = NodesAnalyzer()
    >>> nodes_data = analyzer.check_spherical_nodes(envelope)
"""

import numpy as np
from typing import Dict, Any
from scipy.ndimage import minimum_filter, maximum_filter


class NodesAnalyzer:
    """
    Spherical nodes analyzer for Level B BVP interface.

    Physical Meaning:
        Detects spherical standing wave nodes in the BVP envelope,
        which should be absent in the fundamental field configuration
        according to the 7D phase field theory.

    Mathematical Foundation:
        Analyzes local minima in the field amplitude to detect potential
        nodes and checks for spherical clustering patterns that would
        indicate standing wave behavior.
    """

    def check_spherical_nodes(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Check for absence of spherical standing nodes.

        Physical Meaning:
            Detects spherical standing wave nodes in the BVP envelope,
            which should be absent in the fundamental field configuration
            according to the theory.

        Mathematical Foundation:
            Uses morphological operations to find local minima that could
            be nodes and analyzes their spatial distribution for spherical
            clustering patterns.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - has_spherical_nodes: Boolean indicating presence of spherical nodes
                - node_count: Number of detected potential nodes
                - node_locations: List of node coordinates
        """
        amplitude = np.abs(envelope)

        # Find local minima that could be nodes
        # Use morphological operations to find local minima
        local_minima = minimum_filter(amplitude, size=3) == amplitude
        local_maxima = maximum_filter(amplitude, size=3) == amplitude

        # Nodes are local minima with very low amplitude
        node_threshold = 0.01 * np.max(amplitude)
        potential_nodes = local_minima & (amplitude < node_threshold)

        # Check if nodes form spherical patterns
        node_locations = np.where(potential_nodes)
        node_count = len(node_locations[0])

        # Analyze spherical symmetry of nodes
        has_spherical_nodes = False
        if node_count > 0:
            # Compute center of mass of nodes
            center = np.array(amplitude.shape) // 2
            node_positions = np.column_stack(node_locations)

            # Check if nodes are distributed spherically around center
            distances = np.linalg.norm(node_positions - center, axis=1)
            if len(distances) > 3:
                # Check for spherical clustering
                mean_distance = np.mean(distances)
                std_distance = np.std(distances)
                spherical_coefficient = (
                    std_distance / mean_distance if mean_distance > 0 else 1.0
                )

                # If nodes are clustered in spherical shells, we have spherical nodes
                has_spherical_nodes = spherical_coefficient < 0.3 and node_count > 5

        return {
            "has_spherical_nodes": has_spherical_nodes,
            "node_count": node_count,
            "node_locations": [
                tuple(int(coord) for coord in location)
                for location in zip(*node_locations)
            ],
        }

    def analyze_node_distribution(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze distribution of potential nodes.

        Physical Meaning:
            Analyzes the spatial distribution of potential nodes to
            understand their clustering and symmetry properties.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing node distribution analysis.
        """
        amplitude = np.abs(envelope)

        # Find potential nodes
        local_minima = minimum_filter(amplitude, size=3) == amplitude
        node_threshold = 0.01 * np.max(amplitude)
        potential_nodes = local_minima & (amplitude < node_threshold)

        node_locations = np.where(potential_nodes)
        node_count = len(node_locations[0])

        if node_count == 0:
            return {
                "node_count": 0,
                "spherical_symmetry": 1.0,
                "clustering_coefficient": 0.0,
                "radial_distribution": [],
            }

        # Compute center of mass
        center = np.array(amplitude.shape) // 2
        node_positions = np.column_stack(node_locations)

        # Compute distances from center
        distances = np.linalg.norm(node_positions - center, axis=1)

        # Analyze spherical symmetry
        mean_distance = np.mean(distances)
        std_distance = np.std(distances)
        spherical_symmetry = (
            1.0 - (std_distance / mean_distance) if mean_distance > 0 else 1.0
        )

        # Analyze clustering
        if node_count > 1:
            # Compute pairwise distances
            pairwise_distances = []
            for i in range(node_count):
                for j in range(i + 1, node_count):
                    dist = np.linalg.norm(node_positions[i] - node_positions[j])
                    pairwise_distances.append(dist)

            # Clustering coefficient based on distance variance
            clustering_coefficient = (
                np.std(pairwise_distances) / np.mean(pairwise_distances)
                if pairwise_distances
                else 0.0
            )
        else:
            clustering_coefficient = 0.0

        # Radial distribution
        r_bins = np.linspace(0, np.max(distances), 10)
        radial_distribution = []
        for i in range(len(r_bins) - 1):
            mask = (distances >= r_bins[i]) & (distances < r_bins[i + 1])
            radial_distribution.append(np.sum(mask))

        return {
            "node_count": node_count,
            "spherical_symmetry": float(spherical_symmetry),
            "clustering_coefficient": float(clustering_coefficient),
            "radial_distribution": radial_distribution,
        }
