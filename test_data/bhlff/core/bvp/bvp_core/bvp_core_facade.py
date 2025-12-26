"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Core Facade - Main facade for BVP framework.

This module provides the main facade for the BVP framework, importing and
organizing all BVP core functionality while maintaining the 1 class = 1 file
principle and modular architecture.

Physical Meaning:
    The BVP Core Facade serves as the central backbone of the entire system,
    where all observed particles and fields are manifestations of envelope
    modulations and beatings of the high-frequency carrier field.

Mathematical Foundation:
    BVP implements the envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
    χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.

Example:
    >>> bvp_core = BVPCoreFacade(domain, config, domain_7d)
    >>> envelope = bvp_core.solve_envelope(source)
    >>> quenches = bvp_core.detect_quenches(envelope)
    >>> impedance = bvp_core.compute_impedance(envelope)
"""

# Import the main facade implementation
from .bvp_core_facade_impl import BVPCoreFacade

# Re-export for backward compatibility
__all__ = ["BVPCoreFacade"]
