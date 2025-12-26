"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized phase streamline analysis for Level D models.

This module implements CUDA-accelerated phase streamline analysis with
vectorization for tracing phase gradient flow patterns around defects.

Physical Meaning:
    Phase streamlines represent the flow patterns of phase information
    in the field, revealing the topological structure of phase flow
    around defects using GPU-accelerated gradient computations.

Mathematical Foundation:
    - Phase field: φ(x) = arg[a(x)]
    - Phase gradient: ∇φ = ∇ arg[a(x)] (computed on GPU)
    - Streamlines: dx/dt = ∇φ(x)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from bhlff.utils.cuda_utils import (
    get_optimal_backend,
    CUDA_AVAILABLE as UTILS_CUDA_AVAILABLE,
)


class StreamlineAnalyzerCUDA:
    """
    CUDA-optimized analyzer for phase streamline patterns.

    Physical Meaning:
        Analyzes phase gradient flow patterns using GPU-accelerated
        gradient computations and vectorized streamline tracing.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize CUDA streamline analyzer."""
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA backend
        self.cuda_available = CUDA_AVAILABLE and UTILS_CUDA_AVAILABLE
        if self.cuda_available:
            try:
                self.backend = get_optimal_backend()
            except Exception:
                self.cuda_available = False

        # Initialize analysis tools
        self._gradient_computer = GradientComputerCUDA(
            domain, self.cuda_available, self.backend if self.cuda_available else None
        )
        self._streamline_tracer = StreamlineTracerCUDA(
            domain,
            parameters,
            self.cuda_available,
            self.backend if self.cuda_available else None,
        )
        self._topology_analyzer = TopologyAnalyzerCUDA(domain, self.cuda_available)

        self.logger.info(f"Streamline analyzer CUDA initialized: {self.cuda_available}")

    def trace_phase_streamlines(
        self, field: np.ndarray, center: Tuple[float, ...]
    ) -> Dict[str, Any]:
        """
        Trace phase streamlines around defects with CUDA.

        Physical Meaning:
            Computes streamlines of the phase gradient field using
            GPU-accelerated gradient computation and vectorized operations.

        Args:
            field (np.ndarray): Input field
            center (Tuple): Center point for streamline tracing

        Returns:
            Dict: Streamline analysis results
        """
        self.logger.info("Tracing phase streamlines (CUDA)")

        # Compute field phase
        if self.cuda_available:
            field_gpu = self.backend.array(field)
            phase_gpu = cp.angle(field_gpu)
            phase = self.backend.to_numpy(phase_gpu)
        else:
            phase = np.angle(field)

        # Compute phase gradient with CUDA
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


class GradientComputerCUDA:
    """CUDA-optimized gradient computer."""

    def __init__(self, domain: "Domain", cuda_available: bool = False, backend=None):
        """Initialize CUDA gradient computer."""
        self.domain = domain
        self.cuda_available = cuda_available and (backend is not None)
        self.backend = backend

    def compute_phase_gradient(self, phase: np.ndarray) -> np.ndarray:
        """
        Compute phase gradient field with CUDA.

        Physical Meaning:
            Computes the gradient of the phase field using GPU-accelerated
            vectorized gradient operations.

        Mathematical Foundation:
            ∇φ = (∂φ/∂x, ∂φ/∂y, ∂φ/∂z) computed on GPU

        Args:
            phase (np.ndarray): Phase field

        Returns:
            np.ndarray: Phase gradient field
        """
        if self.cuda_available:
            phase_gpu = self.backend.array(phase)
            if len(phase.shape) == 3:
                grad_x_gpu = cp.gradient(phase_gpu, axis=0)
                grad_y_gpu = cp.gradient(phase_gpu, axis=1)
                grad_z_gpu = cp.gradient(phase_gpu, axis=2)
                gradient_gpu = cp.stack([grad_x_gpu, grad_y_gpu, grad_z_gpu], axis=-1)
                return self.backend.to_numpy(gradient_gpu)
            elif len(phase.shape) == 2:
                grad_x_gpu = cp.gradient(phase_gpu, axis=0)
                grad_y_gpu = cp.gradient(phase_gpu, axis=1)
                gradient_gpu = cp.stack([grad_x_gpu, grad_y_gpu], axis=-1)
                return self.backend.to_numpy(gradient_gpu)
            else:
                gradient_gpu = cp.gradient(phase_gpu)
                gradient_gpu = cp.expand_dims(gradient_gpu, axis=-1)
                return self.backend.to_numpy(gradient_gpu)
        else:
            # CPU fallback
            if len(phase.shape) == 3:
                grad_x = np.gradient(phase, axis=0)
                grad_y = np.gradient(phase, axis=1)
                grad_z = np.gradient(phase, axis=2)
                return np.stack([grad_x, grad_y, grad_z], axis=-1)
            elif len(phase.shape) == 2:
                grad_x = np.gradient(phase, axis=0)
                grad_y = np.gradient(phase, axis=1)
                return np.stack([grad_x, grad_y], axis=-1)
            else:
                gradient = np.gradient(phase)
                return np.expand_dims(gradient, axis=-1)


class StreamlineTracerCUDA:
    """CUDA-optimized streamline tracer."""

    def __init__(
        self,
        domain: "Domain",
        parameters: Dict[str, Any] = None,
        cuda_available: bool = False,
        backend=None,
    ):
        """Initialize CUDA streamline tracer."""
        self.domain = domain
        self.parameters = parameters or {}
        self.cuda_available = cuda_available and (backend is not None)
        self.backend = backend

    def trace_streamlines(
        self, gradient_field: np.ndarray, center: Tuple[float, ...]
    ) -> List[np.ndarray]:
        """
        Trace streamlines in gradient field with CUDA.

        Physical Meaning:
            Traces streamlines using GPU-accelerated interpolation
            and integration operations where possible.

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

        # Trace streamlines (CPU-based integration with GPU-accelerated gradient lookup)
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
        """Trace a single streamline with CUDA acceleration."""
        trajectory = [initial_point.copy()]
        current_point = initial_point.copy()

        for _ in range(integration_steps):
            gradient = self._interpolate_gradient(gradient_field, current_point)
            current_point += step_size * gradient

            if self._is_out_of_bounds(current_point):
                break

            trajectory.append(current_point.copy())

        return np.array(trajectory)

    def _interpolate_gradient(
        self, gradient_field: np.ndarray, point: np.ndarray
    ) -> np.ndarray:
        """Interpolate gradient at given point (GPU-accelerated if available)."""
        if self.cuda_available and len(point) == 3:
            gradient_field_gpu = self.backend.array(gradient_field)
            x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
            y_idx = int(np.clip(point[1], 0, gradient_field.shape[1] - 1))
            z_idx = int(np.clip(point[2], 0, gradient_field.shape[2] - 1))
            gradient_gpu = gradient_field_gpu[x_idx, y_idx, z_idx]
            return self.backend.to_numpy(gradient_gpu)
        else:
            # CPU fallback
            if len(point) == 3:
                x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
                y_idx = int(np.clip(point[1], 0, gradient_field.shape[1] - 1))
                z_idx = int(np.clip(point[2], 0, gradient_field.shape[2] - 1))
                return gradient_field[x_idx, y_idx, z_idx]
            elif len(point) == 2:
                x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
                y_idx = int(np.clip(point[1], 0, gradient_field.shape[1] - 1))
                return gradient_field[x_idx, y_idx]
            else:
                x_idx = int(np.clip(point[0], 0, gradient_field.shape[0] - 1))
                return gradient_field[x_idx]

    def _is_out_of_bounds(self, point: np.ndarray) -> bool:
        """Check if point is out of bounds."""
        for i, coord in enumerate(point):
            if coord < 0 or coord >= self.domain.shape[i]:
                return True
        return False


class TopologyAnalyzerCUDA:
    """CUDA-optimized topology analyzer."""

    def __init__(self, domain: "Domain", cuda_available: bool = False):
        """Initialize CUDA topology analyzer."""
        self.domain = domain
        self.cuda_available = cuda_available

    def analyze_streamline_topology(
        self, streamlines: List[np.ndarray]
    ) -> Dict[str, Any]:
        """
        Analyze topology of streamlines with CUDA.

        Physical Meaning:
            Analyzes the topological structure of streamlines using
            GPU-accelerated computations where applicable.

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

        return {
            "winding_numbers": winding_numbers,
            "topology_class": topology_class,
            "stability_index": stability_index,
            "streamline_density": len(streamlines),
        }

    def _compute_winding_numbers(self, streamlines: List[np.ndarray]) -> List[float]:
        """Compute winding numbers for streamlines."""
        winding_numbers = []
        for streamline in streamlines:
            if len(streamline) > 1:
                winding_number = self._compute_single_winding_number(streamline)
                winding_numbers.append(winding_number)
            else:
                winding_numbers.append(0.0)
        return winding_numbers

    def _compute_single_winding_number(self, streamline: np.ndarray) -> float:
        """Compute winding number for a single streamline."""
        if len(streamline) < 2:
            return 0.0

        total_angle = 0.0
        for i in range(len(streamline) - 1):
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

        lengths = [len(streamline) for streamline in streamlines]
        length_variance = np.var(lengths)
        stability_index = 1.0 / (1.0 + length_variance)

        return float(stability_index)
