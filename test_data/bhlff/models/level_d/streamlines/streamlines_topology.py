"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topology analysis for streamlines.

This module provides topology analysis functionality.
"""

import numpy as np
from typing import Any, Dict, List


class TopologyAnalyzer:
    """Analyze topology of streamlines."""
    
    def __init__(self, domain: "Domain"):
        """Initialize topology analyzer."""
        self.domain = domain
    
    def analyze_streamline_topology(
        self, streamlines: List[np.ndarray]
    ) -> Dict[str, Any]:
        """
        Analyze topology of streamlines.
        
        Physical Meaning:
            Analyzes the topological structure of streamlines,
            including winding numbers, topology classes, and
            stability indices.
        
        Args:
            streamlines (List[np.ndarray]): List of streamline trajectories
        
        Returns:
            Dict: Topology analysis results
        """
        # Compute winding numbers
        winding_numbers = self._compute_winding_numbers(streamlines)
        
        # Compute topology class
        topology_class = self._compute_topology_class(streamlines)
        
        # Compute stability index
        stability_index = self._compute_stability_index(streamlines)
        
        # Compute streamline density
        streamline_density = len(streamlines)
        
        return {
            "winding_numbers": winding_numbers,
            "topology_class": topology_class,
            "stability_index": stability_index,
            "streamline_density": streamline_density,
        }
    
    def _compute_winding_numbers(self, streamlines: List[np.ndarray]) -> List[float]:
        """Compute winding numbers for streamlines."""
        winding_numbers = []
        
        for streamline in streamlines:
            if len(streamline) > 1:
                # Compute winding number
                winding_number = self._compute_single_winding_number(streamline)
                winding_numbers.append(winding_number)
            else:
                winding_numbers.append(0.0)
        
        return winding_numbers
    
    def _compute_single_winding_number(self, streamline: np.ndarray) -> float:
        """Compute winding number for a single streamline."""
        if len(streamline) < 2:
            return 0.0
        
        # Simple winding number computation
        total_angle = 0.0
        for i in range(len(streamline) - 1):
            # Compute angle between consecutive points
            if len(streamline[i]) >= 2:
                angle = np.arctan2(
                    streamline[i + 1][1] - streamline[i][1],
                    streamline[i + 1][0] - streamline[i][0],
                )
                total_angle += angle
        
        winding_number = total_angle / (2 * np.pi)
        return float(winding_number)
    
    def _compute_topology_class(self, streamlines: List[np.ndarray]) -> str:
        """Compute topology class of streamlines."""
        # Simple topology classification
        if len(streamlines) == 0:
            return "empty"
        elif len(streamlines) == 1:
            return "single"
        else:
            return "multiple"
    
    def _compute_stability_index(self, streamlines: List[np.ndarray]) -> float:
        """Compute stability index of streamlines."""
        if len(streamlines) == 0:
            return 0.0
        
        # Simple stability index based on streamline length variance
        lengths = [len(streamline) for streamline in streamlines]
        length_variance = np.var(lengths)
        stability_index = 1.0 / (1.0 + length_variance)
        
        return float(stability_index)

