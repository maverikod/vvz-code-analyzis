"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Layer stack implementation.

This module implements layer stacks for the 7D phase field theory,
providing multiple concentric layers for complex geometries.

Physical Meaning:
    Layer stacks represent multiple concentric spherical layers,
    providing complex geometric structures for phase field
    configurations with multiple boundaries.

Mathematical Foundation:
    Implements multiple spherical layers with proper ordering
    and boundary conditions between layers.

Example:
    >>> stack = LayerStack()
    >>> stack.add_layer(SphericalLayer(0.1, 0.5))
    >>> stack.add_layer(SphericalLayer(0.5, 1.0))
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional

from .spherical_layer import SphericalLayer


class LayerStack:
    """
    Stack of spherical layers for 7D phase field theory.

    Physical Meaning:
        Represents multiple concentric spherical layers forming
        a complex geometric structure for phase field calculations.

    Mathematical Foundation:
        Implements ordered collection of spherical layers with
        proper boundary conditions and layer interactions.

    Attributes:
        layers (List[SphericalLayer]): List of spherical layers.
        center (Tuple[float, float, float]): Common center for all layers.
        _layer_properties (Dict[int, Dict[str, Any]]): Properties for each layer.
    """

    def __init__(self, center: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        """
        Initialize layer stack.

        Physical Meaning:
            Sets up the layer stack with a common center for all
            spherical layers.

        Args:
            center (Tuple[float, float, float]): Common center for all layers.
        """
        self.layers: List[SphericalLayer] = []
        self.center = center
        self._layer_properties: Dict[int, Dict[str, Any]] = {}

    def add_layer(
        self,
        inner_radius: float,
        outer_radius: float,
        properties: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Add a spherical layer to the stack.

        Physical Meaning:
            Adds a new spherical layer to the stack with specified
            inner and outer radii and optional properties.

        Mathematical Foundation:
            Creates new spherical layer and adds it to the ordered
            collection with proper boundary validation.

        Args:
            inner_radius (float): Inner radius of the new layer.
            outer_radius (float): Outer radius of the new layer.
            properties (Dict[str, Any], optional): Properties for the layer.

        Returns:
            int: Index of the added layer.

        Raises:
            ValueError: If layer boundaries conflict with existing layers.
        """
        # Validate layer boundaries
        self._validate_layer_boundaries(inner_radius, outer_radius)

        # Create new layer
        layer = SphericalLayer(
            inner_radius=inner_radius,
            outer_radius=outer_radius,
            center=self.center,
        )

        # Add to stack
        layer_index = len(self.layers)
        self.layers.append(layer)

        # Store properties
        self._layer_properties[layer_index] = properties or {}

        return layer_index

    def _validate_layer_boundaries(
        self, inner_radius: float, outer_radius: float
    ) -> None:
        """
        Validate layer boundaries against existing layers.

        Physical Meaning:
            Ensures that new layer boundaries do not conflict with
            existing layers in the stack.

        Mathematical Foundation:
            Validates that new layer boundaries are consistent with
            existing layer structure.

        Args:
            inner_radius (float): Inner radius of the new layer.
            outer_radius (float): Outer radius of the new layer.

        Raises:
            ValueError: If boundaries conflict with existing layers.
        """
        for layer in self.layers:
            layer_inner, layer_outer = layer.get_radii()

            # Check for overlapping layers
            if not (outer_radius <= layer_inner or inner_radius >= layer_outer):
                raise ValueError(
                    f"Layer boundaries overlap with existing layer "
                    f"({layer_inner}, {layer_outer})"
                )

    def get_layer(self, index: int) -> SphericalLayer:
        """
        Get layer by index.

        Physical Meaning:
            Returns the spherical layer at the specified index.

        Args:
            index (int): Index of the layer.

        Returns:
            SphericalLayer: The requested layer.

        Raises:
            IndexError: If index is out of range.
        """
        if not 0 <= index < len(self.layers):
            raise IndexError(f"Layer index {index} out of range")

        return self.layers[index]

    def get_layer_properties(self, index: int) -> Dict[str, Any]:
        """
        Get properties of a layer.

        Physical Meaning:
            Returns the properties associated with the specified layer.

        Args:
            index (int): Index of the layer.

        Returns:
            Dict[str, Any]: Properties of the layer.

        Raises:
            IndexError: If index is out of range.
        """
        if not 0 <= index < len(self.layers):
            raise IndexError(f"Layer index {index} out of range")

        return self._layer_properties.get(index, {}).copy()

    def set_layer_properties(self, index: int, properties: Dict[str, Any]) -> None:
        """
        Set properties of a layer.

        Physical Meaning:
            Sets the properties associated with the specified layer.

        Args:
            index (int): Index of the layer.
            properties (Dict[str, Any]): Properties to set.

        Raises:
            IndexError: If index is out of range.
        """
        if not 0 <= index < len(self.layers):
            raise IndexError(f"Layer index {index} out of range")

        self._layer_properties[index] = properties.copy()

    def get_total_volume(self) -> float:
        """
        Get total volume of all layers.

        Physical Meaning:
            Computes the total volume of all layers in the stack,
            representing the total volume of the geometric structure.

        Mathematical Foundation:
            Total volume = Σ V_i where V_i is the volume of layer i.

        Returns:
            float: Total volume of all layers.
        """
        total_volume = 0.0
        for layer in self.layers:
            total_volume += layer.get_volume()

        return float(total_volume)

    def get_total_surface_area(self) -> float:
        """
        Get total surface area of all layer boundaries.

        Physical Meaning:
            Computes the total surface area of all layer boundaries,
            representing the total surface area of the geometric structure.

        Mathematical Foundation:
            Total surface area = Σ A_i where A_i is the surface area of layer i.

        Returns:
            float: Total surface area of all layers.
        """
        total_area = 0.0
        for layer in self.layers:
            inner_area, outer_area = layer.get_surface_area()
            total_area += inner_area + outer_area

        return total_area

    def get_layer_containing_point(self, x: float, y: float, z: float) -> Optional[int]:
        """
        Get index of layer containing the specified point.

        Physical Meaning:
            Determines which layer (if any) contains the specified point,
            providing spatial localization within the layer structure.

        Mathematical Foundation:
            Finds layer i such that point (x, y, z) is within layer i boundaries.

        Args:
            x (float): X coordinate of the point.
            y (float): Y coordinate of the point.
            z (float): Z coordinate of the point.

        Returns:
            Optional[int]: Index of containing layer, or None if not found.
        """
        for i, layer in enumerate(self.layers):
            if layer.contains_point(x, y, z):
                return i

        return None

    def get_radial_coordinate(self, x: float, y: float, z: float) -> float:
        """
        Get radial coordinate of a point.

        Physical Meaning:
            Computes the radial distance of a point from the center
            of the layer stack.

        Mathematical Foundation:
            Radial coordinate: r = √((x-cx)² + (y-cy)² + (z-cz)²)

        Args:
            x (float): X coordinate of the point.
            y (float): Y coordinate of the point.
            z (float): Z coordinate of the point.

        Returns:
            float: Radial coordinate.
        """
        dx = x - self.center[0]
        dy = y - self.center[1]
        dz = z - self.center[2]

        return float(np.sqrt(dx**2 + dy**2 + dz**2))

    def get_number_of_layers(self) -> int:
        """
        Get number of layers in the stack.

        Physical Meaning:
            Returns the total number of layers in the stack.

        Returns:
            int: Number of layers.
        """
        return len(self.layers)

    def get_center(self) -> Tuple[float, float, float]:
        """
        Get center coordinates of the stack.

        Physical Meaning:
            Returns the common center coordinates of all layers.

        Returns:
            Tuple[float, float, float]: Center coordinates (x, y, z).
        """
        return self.center

    def clear(self) -> None:
        """
        Clear all layers from the stack.

        Physical Meaning:
            Removes all layers from the stack, resetting it to
            an empty state.
        """
        self.layers.clear()
        self._layer_properties.clear()

    def __repr__(self) -> str:
        """String representation of the layer stack."""
        return f"LayerStack(center={self.center}, " f"num_layers={len(self.layers)})"
