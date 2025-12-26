"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spherical layer implementation.

This module implements spherical layers for the 7D phase field theory,
providing geometric structures for spherical configurations.

Physical Meaning:
    Spherical layers represent concentric spherical shells in the
    computational domain, providing geometric structure for phase
    field configurations with spherical symmetry.

Mathematical Foundation:
    Implements spherical coordinate systems and layer structures
    for 3D phase field calculations with spherical geometry.

Example:
    >>> layer = SphericalLayer(inner_radius=0.1, outer_radius=1.0)
    >>> coordinates = layer.get_coordinates()
"""

import numpy as np
from typing import Tuple


class SphericalLayer:
    """
    Spherical layer for 7D phase field theory.

    Physical Meaning:
        Represents a concentric spherical shell in the computational
        domain, providing geometric structure for phase field
        configurations with spherical symmetry.

    Mathematical Foundation:
        Implements spherical coordinate system (r, θ, φ) with
        layer boundaries defined by inner and outer radii.

    Attributes:
        inner_radius (float): Inner radius of the spherical layer.
        outer_radius (float): Outer radius of the spherical layer.
        center (Tuple[float, float, float]): Center coordinates of the layer.
        resolution (int): Angular resolution for spherical coordinates.
    """

    def __init__(
        self,
        inner_radius: float,
        outer_radius: float,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        resolution: int = 64,
    ) -> None:
        """
        Initialize spherical layer.

        Physical Meaning:
            Sets up the spherical layer with specified inner and outer
            radii, center position, and angular resolution.

        Args:
            inner_radius (float): Inner radius of the spherical layer.
            outer_radius (float): Outer radius of the spherical layer.
            center (Tuple[float, float, float]): Center coordinates.
            resolution (int): Angular resolution for spherical coordinates.

        Raises:
            ValueError: If inner_radius >= outer_radius.
        """
        if inner_radius >= outer_radius:
            raise ValueError("Inner radius must be less than outer radius")

        self.inner_radius = inner_radius
        self.outer_radius = outer_radius
        self.center = center
        self.resolution = resolution

    def get_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get spherical coordinates for the layer.

        Physical Meaning:
            Generates spherical coordinates (r, θ, φ) for the layer,
            providing the coordinate system for phase field calculations.

        Mathematical Foundation:
            Creates spherical coordinate grid:
            - r ∈ [inner_radius, outer_radius]
            - θ ∈ [0, π] (polar angle)
            - φ ∈ [0, 2π] (azimuthal angle)

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: (r, θ, φ) coordinate arrays.
        """
        # Radial coordinates
        r = np.linspace(self.inner_radius, self.outer_radius, self.resolution)

        # Angular coordinates
        theta = np.linspace(0, np.pi, self.resolution)
        phi = np.linspace(0, 2 * np.pi, self.resolution)

        # Create coordinate grids
        R, THETA, PHI = np.meshgrid(r, theta, phi, indexing="ij")

        return R, THETA, PHI

    def get_cartesian_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get Cartesian coordinates for the layer.

        Physical Meaning:
            Converts spherical coordinates to Cartesian coordinates,
            providing the standard coordinate system for computations.

        Mathematical Foundation:
            Converts (r, θ, φ) to (x, y, z):
            x = r sin(θ) cos(φ) + center_x
            y = r sin(θ) sin(φ) + center_y
            z = r cos(θ) + center_z

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: (x, y, z) coordinate arrays.
        """
        R, THETA, PHI = self.get_coordinates()

        # Convert to Cartesian coordinates
        X = R * np.sin(THETA) * np.cos(PHI) + self.center[0]
        Y = R * np.sin(THETA) * np.sin(PHI) + self.center[1]
        Z = R * np.cos(THETA) + self.center[2]

        return X, Y, Z

    def get_volume(self) -> float:
        """
        Get volume of the spherical layer.

        Physical Meaning:
            Computes the volume of the spherical layer, representing
            the total volume enclosed by the layer boundaries.

        Mathematical Foundation:
            Volume of spherical layer: V = (4/3)π(R_outer³ - R_inner³)

        Returns:
            float: Volume of the spherical layer.
        """
        volume = (4.0 / 3.0) * np.pi * (self.outer_radius**3 - self.inner_radius**3)
        return float(volume)

    def get_surface_area(self) -> Tuple[float, float]:
        """
        Get surface areas of the layer boundaries.

        Physical Meaning:
            Computes the surface areas of the inner and outer
            boundaries of the spherical layer.

        Mathematical Foundation:
            Surface area of sphere: A = 4πR²

        Returns:
            Tuple[float, float]: (inner_surface_area, outer_surface_area).
        """
        inner_area = 4.0 * np.pi * self.inner_radius**2
        outer_area = 4.0 * np.pi * self.outer_radius**2

        return inner_area, outer_area

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """
        Check if point is inside the spherical layer.

        Physical Meaning:
            Determines whether a given point lies within the
            spherical layer boundaries.

        Mathematical Foundation:
            Point (x, y, z) is inside if:
            inner_radius² ≤ (x-cx)² + (y-cy)² + (z-cz)² ≤ outer_radius²

        Args:
            x (float): X coordinate of the point.
            y (float): Y coordinate of the point.
            z (float): Z coordinate of the point.

        Returns:
            bool: True if point is inside the layer.
        """
        # Calculate distance from center
        dx = x - self.center[0]
        dy = y - self.center[1]
        dz = z - self.center[2]
        distance_squared = dx**2 + dy**2 + dz**2

        # Check if within layer boundaries
        inner_squared = self.inner_radius**2
        outer_squared = self.outer_radius**2

        return inner_squared <= distance_squared <= outer_squared

    def get_layer_thickness(self) -> float:
        """
        Get thickness of the spherical layer.

        Physical Meaning:
            Computes the radial thickness of the spherical layer,
            representing the distance between inner and outer boundaries.

        Mathematical Foundation:
            Thickness = outer_radius - inner_radius

        Returns:
            float: Thickness of the spherical layer.
        """
        return self.outer_radius - self.inner_radius

    def get_center(self) -> Tuple[float, float, float]:
        """
        Get center coordinates of the layer.

        Physical Meaning:
            Returns the center coordinates of the spherical layer.

        Returns:
            Tuple[float, float, float]: Center coordinates (x, y, z).
        """
        return self.center

    def get_radii(self) -> Tuple[float, float]:
        """
        Get inner and outer radii of the layer.

        Physical Meaning:
            Returns the inner and outer radii of the spherical layer.

        Returns:
            Tuple[float, float]: (inner_radius, outer_radius).
        """
        return self.inner_radius, self.outer_radius

    def __repr__(self) -> str:
        """String representation of the spherical layer."""
        return (
            f"SphericalLayer(inner_radius={self.inner_radius}, "
            f"outer_radius={self.outer_radius}, "
            f"center={self.center})"
        )
