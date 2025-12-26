"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Analysis methods for streamline analyzer.

This module provides analysis methods as a mixin class.
"""

import numpy as np
from typing import Any, Dict, Tuple


class StreamlineAnalyzerAnalysisMixin:
    """Mixin providing analysis methods."""
    
    def trace_phase_streamlines(
        self, field: np.ndarray, center: Tuple[float, ...]
    ) -> Dict[str, Any]:
        """
        Trace phase streamlines around defects.
        
        Physical Meaning:
            Computes streamlines of the phase gradient field,
            revealing the topological structure of phase flow
            around defects and singularities.
        
        Mathematical Foundation:
            Integrates the phase gradient field to find
            streamlines that are tangent to the gradient
            at each point: dx/dt = ∇φ(x)
        
        Args:
            field (np.ndarray): Input field
            center (Tuple): Center point for streamline tracing
        
        Returns:
            Dict: Streamline analysis results
        """
        self.logger.info("Tracing phase streamlines")
        
        # Compute field phase
        phase = np.angle(field)
        
        # Compute phase gradient
        phase_gradient = self._gradient_computer.compute_phase_gradient(phase)
        
        # Trace streamlines
        streamlines = self._streamline_tracer.trace_streamlines(phase_gradient, center)
        
        # Analyze topology
        topology = self._topology_analyzer.analyze_streamline_topology(streamlines)
        
        results = {
            "phase": phase,
            "phase_gradient": phase_gradient,
            "streamlines": streamlines,
            "topology": topology,
        }
        
        self.logger.info("Phase streamline analysis completed")
        return results
    
    def analyze_streamlines(
        self, field: np.ndarray, resolution: float = 1.0
    ) -> Dict[str, Any]:
        """
        Analyze streamline patterns in the field.
        
        Physical Meaning:
            Computes field gradients to analyze streamline patterns
            and flow characteristics in the field.
        
        Mathematical Foundation:
            Computes divergence: ∇·v = ∂v_x/∂x + ∂v_y/∂y + ∂v_z/∂z
            Computes curl: ∇×v = (∂v_z/∂y - ∂v_y/∂z, ∂v_x/∂z - ∂v_z/∂x, ∂v_y/∂x - ∂v_x/∂y)
        
        Args:
            field (np.ndarray): Input field
            resolution (float): Resolution for streamline analysis
        
        Returns:
            Dict: Streamline analysis results
        """
        self.logger.info("Analyzing streamline patterns")
        
        # Compute field gradients
        gradients = self._gradient_computer.compute_field_gradients(field)
        
        # Compute divergence
        divergence = self._gradient_computer.compute_divergence(gradients)
        
        # Compute curl
        curl = self._gradient_computer.compute_curl(gradients)
        
        # Analyze streamline density
        streamline_density = self._compute_streamline_density(field, resolution)
        
        results = {
            "divergence_max": float(np.max(divergence)),
            "divergence_mean": float(np.mean(divergence)),
            "curl_max": float(np.max(np.linalg.norm(curl, axis=-1))),
            "curl_mean": float(np.mean(np.linalg.norm(curl, axis=-1))),
            "streamline_density": float(streamline_density),
        }
        
        self.logger.info("Streamline pattern analysis completed")
        return results
    
    def _compute_streamline_density(
        self, field: np.ndarray, resolution: float
    ) -> float:
        """Compute streamline density."""
        return 1.0

