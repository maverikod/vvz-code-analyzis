"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Streamline tracing for streamlines.

This module provides streamline tracing functionality.
"""

import numpy as np
from typing import Any, Dict, List, Optional, Tuple


class StreamlineTracer:
    """Trace streamlines in gradient field."""
    
    def __init__(self, domain: "Domain", parameters: Optional[Dict[str, Any]] = None):
        """Initialize streamline tracer."""
        self.domain = domain
        self.parameters = parameters or {}
    
    def trace_streamlines(
        self, gradient_field: np.ndarray, center: Tuple[float, ...]
    ) -> List[np.ndarray]:
        """
        Trace streamlines in gradient field.
        
        Physical Meaning:
            Traces streamlines that are tangent to the
            gradient field at each point, revealing
            the flow patterns of the field.
        
        Mathematical Foundation:
            Integrates the differential equation:
            dx/dt = ∇φ(x)
            where ∇φ is the gradient field.
        
        Args:
            gradient_field (np.ndarray): Gradient field
            center (Tuple): Center point for streamline tracing
        
        Returns:
            List[np.ndarray]: List of streamline trajectories
        """
        # Extract parameters
        num_streamlines = self.parameters.get("num_streamlines", 100)
        integration_steps = self.parameters.get("integration_steps", 1000)
        step_size = self.parameters.get("step_size", 0.01)
        
        # Create initial points around center
        initial_points = self._create_initial_points(center, num_streamlines)
        
        # Trace streamlines
        streamlines = []
        for point in initial_points:
            streamline = self._trace_single_streamline(
                gradient_field, point, integration_steps, step_size
            )
            streamlines.append(streamline)
        
        return streamlines
    
    def _create_initial_points(
        self, center: Tuple[float, ...], num_points: int
    ) -> List[np.ndarray]:
        """Create initial points for streamline tracing."""
        points = []
        
        if len(center) == 3:
            # 3D initial points
            radius = 0.1
            for i in range(num_points):
                angle = 2 * np.pi * i / num_points
                point = np.array(
                    [
                        center[0] + radius * np.cos(angle),
                        center[1] + radius * np.sin(angle),
                        center[2],
                    ]
                )
                points.append(point)
        elif len(center) == 2:
            # 2D initial points
            radius = 0.1
            for i in range(num_points):
                angle = 2 * np.pi * i / num_points
                point = np.array(
                    [
                        center[0] + radius * np.cos(angle),
                        center[1] + radius * np.sin(angle),
                    ]
                )
                points.append(point)
        else:
            # 1D initial points
            for i in range(num_points):
                point = np.array([center[0] + 0.1 * i / num_points])
                points.append(point)
        
        return points
    
    def _trace_single_streamline(
        self,
        gradient_field: np.ndarray,
        initial_point: np.ndarray,
        integration_steps: int,
        step_size: float,
    ) -> np.ndarray:
        """Trace a single streamline."""
        # Initialize trajectory
        trajectory = [initial_point.copy()]
        current_point = initial_point.copy()
        
        # Integrate streamline
        for _ in range(integration_steps):
            # Get gradient at current point
            gradient = self._interpolate_gradient(gradient_field, current_point)
            
            # Update point
            current_point += step_size * gradient
            
            # Check bounds
            if self._is_out_of_bounds(current_point):
                break
            
            # Add to trajectory
            trajectory.append(current_point.copy())
        
        return np.array(trajectory)
    
    def _interpolate_gradient(
        self, gradient_field: np.ndarray, point: np.ndarray
    ) -> np.ndarray:
        """Interpolate gradient at given point."""
        # Simple nearest neighbor interpolation
        if len(point) == 3:
            x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
            y_idx = int(np.clip(point[1], 0, gradient_field.shape[1] - 1))
            z_idx = int(np.clip(point[2], 0, gradient_field.shape[2] - 1))
            gradient = gradient_field[x_idx, y_idx, z_idx]
        elif len(point) == 2:
            x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
            y_idx = int(np.clip(point[1], 0, gradient_field.shape[1] - 1))
            gradient = gradient_field[x_idx, y_idx]
        else:
            x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
            gradient = gradient_field[x_idx]
        
        return gradient
    
    def _is_out_of_bounds(self, point: np.ndarray) -> bool:
        """Check if point is out of bounds."""
        for i, coord in enumerate(point):
            if coord < 0 or coord >= self.domain.shape[i]:
                return True
        return False

