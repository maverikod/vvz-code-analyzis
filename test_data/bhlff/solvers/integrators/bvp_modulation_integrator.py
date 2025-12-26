"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP-modulated time integrator implementation.

This module implements the BVP-modulated time integrator for the 7D phase
field theory, providing temporal evolution with BVP modulation.

Physical Meaning:
    BVP-modulated integrator implements temporal evolution of phase field
    configurations with modulation by the Base High-Frequency Field,
    representing the temporal dynamics of BVP-modulated systems.

Mathematical Foundation:
    Implements time integration for BVP-modulated equations:
    ∂a/∂t = F_BVP(a, t) + modulation_terms
    where F_BVP represents BVP-specific evolution terms.

Example:
    >>> integrator = BVPModulationIntegrator(domain, config)
    >>> field_next = integrator.step(field_current, dt)
"""

from .bvp_modulation_integrator_core import BVPModulationIntegrator

__all__ = ["BVPModulationIntegrator"]
