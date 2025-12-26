"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Geometry package for BHLFF framework.

This package provides geometric components including layers, boundaries,
and spatial structures for the 7D phase field theory.

Physical Meaning:
    Geometry components define the spatial structure of the computational
    domain, including layer configurations, boundary conditions, and
    geometric constraints for phase field simulations.

Mathematical Foundation:
    Implements geometric structures for 7D space-time including spherical
    layers, boundary conditions, and spatial discretization schemes.
"""

from .layers import SphericalLayer, LayerStack

__all__ = [
    "SphericalLayer",
    "LayerStack",
]
