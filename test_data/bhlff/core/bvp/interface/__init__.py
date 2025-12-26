"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Interface package for modular interface components.

This package provides modular interface components for BVP framework,
including tail interface, transition zone interface, and core interface
functionality.

Theoretical Background:
    The BVP interface serves as the connection point between the BVP
    envelope and other system components. This package provides modular
    components for different interface types.

Example:
    >>> from bhlff.core.bvp.interface import BVPInterface
    >>> interface = BVPInterface(bvp_core)
    >>> tail_data = interface.interface_with_tail(envelope)
"""

from .interface_facade import BVPInterface
from .tail_interface import TailInterface
from .transition_interface import TransitionInterface
from .core_interface import CoreInterface

__all__ = ["BVPInterface", "TailInterface", "TransitionInterface", "CoreInterface"]
