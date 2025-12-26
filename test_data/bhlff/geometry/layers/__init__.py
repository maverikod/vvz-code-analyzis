"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Layers package for BHLFF framework.

This package provides layer components for the 7D phase field theory,
including spherical layers and layer stacks.

Physical Meaning:
    Layers implement geometric structures for phase field configurations,
    providing spatial organization and boundary conditions.

Mathematical Foundation:
    Implements spherical coordinate systems and layer structures
    for 3D phase field calculations with spherical geometry.
"""

from .spherical_layer import SphericalLayer
from .layer_stack import LayerStack

__all__ = [
    "SphericalLayer",
    "LayerStack",
]
