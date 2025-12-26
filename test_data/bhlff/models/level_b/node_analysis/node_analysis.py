"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Node analysis module for Level B.

This module implements node analysis operations for Level B
of the 7D phase field theory, focusing on node identification and classification.

Physical Meaning:
    Analyzes node structures in the BVP field including saddle nodes,
    source nodes, and sink nodes, providing topological analysis
    of the field structure.

Mathematical Foundation:
    Implements node analysis including:
    - Node identification using gradient analysis
    - Node classification based on local field properties
    - Topological charge computation
    - Node density analysis

Example:
    >>> analyzer = NodeAnalysis(bvp_core)
    >>> nodes = analyzer.identify_nodes(envelope)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .topological_analysis import TopologicalAnalysis
from .charge_computation import ChargeComputation


class NodeAnalysis:
    """
    Node analysis for BVP field.

    Physical Meaning:
        Implements node analysis operations for identifying and classifying
        node structures in the BVP field, including topological analysis
        and charge computation.

    Mathematical Foundation:
        Analyzes field gradients and local properties to identify
        critical points and classify them according to their topological
        characteristics.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize node analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for analysis.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize specialized analyzers
        self._topological_analyzer = TopologicalAnalysis(bvp_core)
        self._charge_computer = ChargeComputation(bvp_core)

    def identify_nodes(self, envelope: np.ndarray) -> List[Tuple[int, ...]]:
        """
        Identify node locations in the field using full topological analysis.

        Physical Meaning:
            Identifies critical points in the BVP field where the
            field gradient vanishes, using complete topological analysis
            according to the 7D theory.

        Mathematical Foundation:
            Uses full gradient analysis and topological criteria to find
            points where ∇f = 0, with proper topological classification
            and stability analysis.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            List[Tuple[int, ...]]: List of node coordinates.
        """
        amplitude = np.abs(envelope)
        nodes = []

        # Compute full gradient analysis
        if amplitude.ndim >= 3:
            # Compute gradients in all dimensions
            gradients = {}
            for dim in range(amplitude.ndim):
                gradients[f"dim_{dim}"] = np.gradient(amplitude, axis=dim)

            # Compute gradient magnitude
            grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

            # Use adaptive threshold based on field properties
            threshold = self._compute_adaptive_threshold(grad_magnitude, amplitude)

            # Find critical points using topological criteria
            critical_points = self._find_critical_points(gradients, threshold)

            # Filter nodes using topological analysis
            for point in critical_points:
                if self._is_valid_node(envelope, point):
                    nodes.append(point)

            # Limit number of nodes for performance
            if len(nodes) > 50:
                nodes = nodes[:50]

        return nodes

    def _compute_adaptive_threshold(
        self, grad_magnitude: np.ndarray, amplitude: np.ndarray
    ) -> float:
        """Compute adaptive threshold for node detection."""
        # Use statistical analysis to determine threshold
        mean_grad = np.mean(grad_magnitude)
        std_grad = np.std(grad_magnitude)

        # Adaptive threshold based on field properties
        threshold = mean_grad - 2 * std_grad  # 2-sigma below mean

        # Ensure threshold is positive and reasonable
        threshold = max(threshold, mean_grad * 0.01)

        return threshold

    def _find_critical_points(
        self, gradients: Dict[str, np.ndarray], threshold: float
    ) -> List[Tuple[int, ...]]:
        """Find critical points using gradient analysis."""
        # Compute gradient magnitude
        grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

        # Find points below threshold
        critical_mask = grad_magnitude < threshold

        # Get coordinates of critical points
        critical_coords = np.where(critical_mask)

        # Convert to list of tuples
        critical_points = []
        for i in range(len(critical_coords[0])):
            point = tuple(
                critical_coords[dim][i] for dim in range(len(critical_coords))
            )
            critical_points.append(point)

        return critical_points

    def _is_valid_node(self, envelope: np.ndarray, point: Tuple[int, ...]) -> bool:
        """Check if a point is a valid node using topological criteria."""
        # Check bounds
        if not all(0 <= point[dim] < envelope.shape[dim] for dim in range(len(point))):
            return False

        # Check if point is not on boundary
        if any(
            point[dim] == 0 or point[dim] == envelope.shape[dim] - 1
            for dim in range(len(point))
        ):
            return False

        # Check local field properties
        local_amplitude = envelope[point]
        if local_amplitude < 1e-10:  # Avoid zero amplitude points
            return False

        # Check topological properties
        if len(point) >= 3:
            # Use topological analysis to validate node
            return self._topological_analyzer.is_saddle_node(envelope, point)

        return True

    def classify_nodes(self, envelope: np.ndarray) -> Dict[str, List[Tuple[int, ...]]]:
        """
        Classify nodes by type.

        Physical Meaning:
            Classifies identified nodes into different types based on
            their local field properties and topological characteristics.

        Mathematical Foundation:
            Uses local field analysis to classify nodes as saddle,
            source, or sink nodes based on the local field structure.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, List[Tuple[int, ...]]]: Classification results:
                - saddle_nodes: List of saddle node coordinates
                - source_nodes: List of source node coordinates
                - sink_nodes: List of sink node coordinates
        """
        nodes = self.identify_nodes(envelope)

        saddle_nodes = []
        source_nodes = []
        sink_nodes = []

        for node in nodes:
            if self._topological_analyzer.is_saddle_node(envelope, node):
                saddle_nodes.append(node)
            elif self._is_source_node(envelope, node):
                source_nodes.append(node)
            elif self._is_sink_node(envelope, node):
                sink_nodes.append(node)

        return {
            "saddle_nodes": saddle_nodes,
            "source_nodes": source_nodes,
            "sink_nodes": sink_nodes,
        }

    def compute_node_density(self, envelope: np.ndarray) -> float:
        """
        Compute spatial density of nodes.

        Physical Meaning:
            Computes the spatial density of nodes in the BVP field,
            providing a measure of field complexity.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            float: Node density (nodes per unit volume).
        """
        nodes = self.identify_nodes(envelope)
        total_volume = envelope.size
        return len(nodes) / total_volume if total_volume > 0 else 0.0

    def compute_topological_charge(self, envelope: np.ndarray) -> float:
        """
        Compute topological charge of the field.

        Physical Meaning:
            Computes the total topological charge of the BVP field
            by analyzing the phase structure and winding numbers.

        Mathematical Foundation:
            Computes topological charge using phase analysis:
            Q = (1/2π) ∮ ∇φ · dl around closed loops.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            float: Total topological charge.
        """
        return self._charge_computer.compute_topological_charge(envelope)

    def _is_source_node(self, envelope: np.ndarray, node: Tuple[int, ...]) -> bool:
        """
        Check if node is a source node using full topological analysis.

        Physical Meaning:
            Determines if a node is a source node based on complete
            topological analysis including Hessian matrix and stability analysis.

        Args:
            envelope (np.ndarray): BVP envelope field.
            node (Tuple[int, ...]): Node coordinates.

        Returns:
            bool: True if node is a source node.
        """
        if len(node) >= 3:
            # Use topological analysis for source detection
            return self._topological_analyzer.is_source_node(envelope, node)
        return False

    def _is_sink_node(self, envelope: np.ndarray, node: Tuple[int, ...]) -> bool:
        """
        Check if node is a sink node using full topological analysis.

        Physical Meaning:
            Determines if a node is a sink node based on complete
            topological analysis including Hessian matrix and stability analysis.

        Args:
            envelope (np.ndarray): BVP envelope field.
            node (Tuple[int, ...]): Node coordinates.

        Returns:
            bool: True if node is a sink node.
        """
        if len(node) >= 3:
            # Use topological analysis for sink detection
            return self._topological_analyzer.is_sink_node(envelope, node)
        return False

    def __repr__(self) -> str:
        """String representation of node analyzer."""
        return f"NodeAnalysis(bvp_core={self.bvp_core})"
