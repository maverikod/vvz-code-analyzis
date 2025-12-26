"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP core package for 7D space-time theory.

This package contains the modular implementation of the BVP core framework,
implementing the central backbone of the 7D theory where all observed
"modes" are envelope modulations and beatings of the Base High-Frequency Field.

Physical Meaning:
    The BVP core serves as the central backbone of the entire system, where
    all observed particles and fields are manifestations of envelope
    modulations and beatings of the high-frequency carrier field.

Mathematical Foundation:
    BVP implements the envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x)
    where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
    χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.

Example:
    >>> from bhlff.core.bvp.bvp_core import BVPCore
    >>> bvp_core = BVPCore(domain, config)
    >>> envelope = bvp_core.solve_envelope(source)
"""

from .bvp_core_facade import BVPCoreFacade
from .bvp_operations import BVPCoreOperations
from .bvp_7d_interface import BVPCore7DInterface

# Main facade class for unified interface
BVPCore = BVPCoreFacade

__all__ = ["BVPCore", "BVPCoreFacade", "BVPCoreOperations", "BVPCore7DInterface"]
