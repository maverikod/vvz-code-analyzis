"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D space-time domain implementation.

This module implements the full 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
for the BVP framework, including spatial coordinates, phase coordinates,
and temporal evolution.

Physical Meaning:
    Implements the fundamental 7D space-time structure where:
    - ℝ³ₓ: 3 spatial coordinates (x, y, z) - conventional geometry
    - 𝕋³_φ: 3 phase coordinates (φ₁, φ₂, φ₃) - internal field states
    - ℝₜ: 1 temporal coordinate (t) - evolution dynamics

Mathematical Foundation:
    The 7D space-time M₇ provides the foundation for all BVP calculations,
    with proper coordinate transformations and metric structure.

Example:
    >>> domain_7d = Domain7D(spatial_config, phase_config, temporal_config)
    >>> coordinates = domain_7d.get_coordinates()
    >>> metric = domain_7d.get_metric_tensor()
"""

import numpy as np
from typing import Dict, Any, Tuple, List

from .domain import Domain
from .config import SpatialConfig, PhaseConfig, TemporalConfig


class Domain7D:
    """
    7D space-time domain for BVP framework.

    Physical Meaning:
        Implements the full 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
        providing the foundation for all BVP calculations with proper
        coordinate transformations and metric structure.

    Mathematical Foundation:
        The 7D space-time provides:
        - Spatial coordinates: x ∈ ℝ³
        - Phase coordinates: φ ∈ 𝕋³ (periodic)
        - Temporal coordinate: t ∈ ℝ
        - Metric tensor: g_μν for proper distance calculations
    """

    def __init__(
        self,
        spatial_config: SpatialConfig,
        phase_config: PhaseConfig,
        temporal_config: TemporalConfig,
    ):
        """
        Initialize 7D space-time domain.

        Physical Meaning:
            Sets up the complete 7D space-time structure with spatial,
            phase, and temporal coordinates for BVP calculations.

        Args:
            spatial_config (SpatialConfig): Configuration for spatial coordinates.
            phase_config (PhaseConfig): Configuration for phase coordinates.
            temporal_config (TemporalConfig): Configuration for temporal coordinate.
        """
        self.spatial_config = spatial_config
        self.phase_config = phase_config
        self.temporal_config = temporal_config

        # Set dimensions for 7D BVP theory
        self.dimensions = 7

        self._setup_spatial_coordinates()
        self._setup_phase_coordinates()
        self._setup_temporal_coordinates()
        self._setup_metric_tensor()

    def _setup_spatial_coordinates(self) -> None:
        """Setup spatial coordinates ℝ³ₓ."""
        # Spatial grid points
        self.x = np.linspace(0, self.spatial_config.L_x, self.spatial_config.N_x)
        self.y = np.linspace(0, self.spatial_config.L_y, self.spatial_config.N_y)
        self.z = np.linspace(0, self.spatial_config.L_z, self.spatial_config.N_z)

        # Spatial coordinate grids
        self.X, self.Y, self.Z = np.meshgrid(self.x, self.y, self.z, indexing="ij")

        # Spatial differentials
        self.dx = self.spatial_config.L_x / (self.spatial_config.N_x - 1)
        self.dy = self.spatial_config.L_y / (self.spatial_config.N_y - 1)
        self.dz = self.spatial_config.L_z / (self.spatial_config.N_z - 1)

    def _setup_phase_coordinates(self) -> None:
        """Setup phase coordinates 𝕋³_φ."""
        # Phase grid points (periodic)
        self.phi_1 = np.linspace(
            0, self.phase_config.phi_1_max, self.phase_config.N_phi_1, endpoint=False
        )
        self.phi_2 = np.linspace(
            0, self.phase_config.phi_2_max, self.phase_config.N_phi_2, endpoint=False
        )
        self.phi_3 = np.linspace(
            0, self.phase_config.phi_3_max, self.phase_config.N_phi_3, endpoint=False
        )

        # Phase coordinate grids
        self.PHI_1, self.PHI_2, self.PHI_3 = np.meshgrid(
            self.phi_1, self.phi_2, self.phi_3, indexing="ij"
        )

        # Phase differentials
        self.dphi_1 = self.phase_config.phi_1_max / self.phase_config.N_phi_1
        self.dphi_2 = self.phase_config.phi_2_max / self.phase_config.N_phi_2
        self.dphi_3 = self.phase_config.phi_3_max / self.phase_config.N_phi_3

    def _setup_temporal_coordinates(self) -> None:
        """Setup temporal coordinate ℝₜ."""
        # Temporal grid points
        self.t = np.linspace(0, self.temporal_config.T_max, self.temporal_config.N_t)

        # Temporal differential
        self.dt = self.temporal_config.dt

    def _setup_metric_tensor(self) -> None:
        """Setup metric tensor for 7D space-time."""
        # Create full 7D coordinate grids
        self._create_full_coordinate_grids()

        # Metric tensor components (flat metric for now)
        self.metric_spatial = np.eye(3)  # Spatial metric
        self.metric_phase = np.eye(3)  # Phase metric
        self.metric_temporal = -1.0  # Temporal metric (Minkowski-like)

        # Full 7D metric tensor
        self.metric_7d = np.zeros((7, 7))
        self.metric_7d[0:3, 0:3] = self.metric_spatial
        self.metric_7d[3:6, 3:6] = self.metric_phase
        self.metric_7d[6, 6] = self.metric_temporal

    def _create_full_coordinate_grids(self) -> None:
        """Create full 7D coordinate grids."""
        # Full 7D coordinate arrays
        self.coords_7d = np.zeros(
            (
                7,
                self.spatial_config.N_x,
                self.spatial_config.N_y,
                self.spatial_config.N_z,
                self.phase_config.N_phi_1,
                self.phase_config.N_phi_2,
                self.phase_config.N_phi_3,
            )
        )

        # Fill coordinate arrays
        for i in range(self.spatial_config.N_x):
            for j in range(self.spatial_config.N_y):
                for k in range(self.spatial_config.N_z):
                    for l in range(self.phase_config.N_phi_1):
                        for m in range(self.phase_config.N_phi_2):
                            for n in range(self.phase_config.N_phi_3):
                                self.coords_7d[0, i, j, k, l, m, n] = self.x[i]
                                self.coords_7d[1, i, j, k, l, m, n] = self.y[j]
                                self.coords_7d[2, i, j, k, l, m, n] = self.z[k]
                                self.coords_7d[3, i, j, k, l, m, n] = self.phi_1[l]
                                self.coords_7d[4, i, j, k, l, m, n] = self.phi_2[m]
                                self.coords_7d[5, i, j, k, l, m, n] = self.phi_3[n]

    def get_spatial_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get spatial coordinates ℝ³ₓ.

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: (X, Y, Z) coordinate grids.
        """
        return self.X, self.Y, self.Z

    def get_phase_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get phase coordinates 𝕋³_φ.

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: (PHI_1, PHI_2, PHI_3) coordinate grids.
        """
        return self.PHI_1, self.PHI_2, self.PHI_3

    def get_temporal_coordinates(self) -> np.ndarray:
        """
        Get temporal coordinates ℝₜ.

        Returns:
            np.ndarray: Temporal coordinate array.
        """
        return self.t

    def get_full_7d_coordinates(self) -> np.ndarray:
        """
        Get full 7D coordinate array.

        Returns:
            np.ndarray: Full 7D coordinate array with shape (7, N_x, N_y, N_z, N_phi_1, N_phi_2, N_phi_3).
        """
        return self.coords_7d

    def get_metric_tensor(self) -> np.ndarray:
        """
        Get 7D metric tensor.

        Returns:
            np.ndarray: 7D metric tensor with shape (7, 7).
        """
        return self.metric_7d

    def get_spatial_shape(self) -> Tuple[int, int, int]:
        """
        Get spatial grid shape.

        Returns:
            Tuple[int, int, int]: (N_x, N_y, N_z) spatial grid dimensions.
        """
        return (
            self.spatial_config.N_x,
            self.spatial_config.N_y,
            self.spatial_config.N_z,
        )

    def get_phase_shape(self) -> Tuple[int, int, int]:
        """
        Get phase grid shape.

        Returns:
            Tuple[int, int, int]: (N_phi_1, N_phi_2, N_phi_3) phase grid dimensions.
        """
        return (
            self.phase_config.N_phi_1,
            self.phase_config.N_phi_2,
            self.phase_config.N_phi_3,
        )

    def get_full_7d_shape(self) -> Tuple[int, int, int, int, int, int]:
        """
        Get full 7D grid shape.

        Returns:
            Tuple[int, int, int, int, int, int]: Full 7D grid dimensions.
        """
        return (
            self.spatial_config.N_x,
            self.spatial_config.N_y,
            self.spatial_config.N_z,
            self.phase_config.N_phi_1,
            self.phase_config.N_phi_2,
            self.phase_config.N_phi_3,
        )

    @property
    def shape(self) -> Tuple[int, int, int, int, int, int, int]:
        """
        Get full 7D grid shape including temporal dimension.

        Physical Meaning:
            Returns the complete 7D grid shape including spatial,
            phase, and temporal dimensions for BVP calculations.

        Returns:
            Tuple[int, int, int, int, int, int, int]: Full 7D grid shape
                (N_x, N_y, N_z, N_phi_1, N_phi_2, N_phi_3, N_t).
        """
        return (
            self.spatial_config.N_x,
            self.spatial_config.N_y,
            self.spatial_config.N_z,
            self.phase_config.N_phi_1,
            self.phase_config.N_phi_2,
            self.phase_config.N_phi_3,
            self.temporal_config.N_t,
        )

    def get_differentials(self) -> Dict[str, float]:
        """
        Get coordinate differentials.

        Returns:
            Dict[str, float]: Dictionary of coordinate differentials.
        """
        return {
            "dx": self.dx,
            "dy": self.dy,
            "dz": self.dz,
            "dphi_1": self.dphi_1,
            "dphi_2": self.dphi_2,
            "dphi_3": self.dphi_3,
            "dt": self.dt,
        }

    def compute_7d_volume_element(self) -> np.ndarray:
        """
        Compute 7D volume element.

        Physical Meaning:
            Computes the volume element dV₇ for integration over the 7D space-time.

        Mathematical Foundation:
            dV₇ = dx dy dz dφ₁ dφ₂ dφ₃ dt

        Returns:
            np.ndarray: 7D volume element array.
        """
        volume_element = (
            self.dx
            * self.dy
            * self.dz
            * self.dphi_1
            * self.dphi_2
            * self.dphi_3
            * self.dt
        )
        return volume_element

    def compute_7d_distance(self, point1: np.ndarray, point2: np.ndarray) -> float:
        """
        Compute 7D distance between two points.

        Physical Meaning:
            Computes the proper distance between two points in 7D space-time
            using the metric tensor.

        Mathematical Foundation:
            ds² = g_μν dx^μ dx^ν

        Args:
            point1 (np.ndarray): First point in 7D space-time.
            point2 (np.ndarray): Second point in 7D space-time.

        Returns:
            float: 7D distance between the points.
        """
        diff = point2 - point1
        distance_squared = np.dot(diff, np.dot(self.metric_7d, diff))
        return np.sqrt(np.abs(distance_squared))

    def __repr__(self) -> str:
        """String representation of 7D domain."""
        return (
            f"Domain7D(spatial=({self.spatial_config.N_x}x{self.spatial_config.N_y}x{self.spatial_config.N_z}), "
            f"phase=({self.phase_config.N_phi_1}x{self.phase_config.N_phi_2}x{self.phase_config.N_phi_3}), "
            f"temporal={self.temporal_config.N_t})"
        )
