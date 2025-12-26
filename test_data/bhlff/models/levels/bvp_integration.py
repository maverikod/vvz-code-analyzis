"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP integration module for all levels A-G - Main facade.

This module provides the main facade for BVP integration with all levels
of the 7D phase field theory, importing and organizing all integration
components while maintaining the 1 class = 1 file principle.

Physical Meaning:
    Provides unified integration interface between BVP framework and
    all levels of the 7D theory, ensuring consistent data flow and
    proper coordination between different system components.

Mathematical Foundation:
    Implements integration protocols that transform BVP envelope data
    into appropriate formats for each level while maintaining
    physical consistency and mathematical rigor.

Example:
    >>> integrator = BVPLevelIntegrator(bvp_core)
    >>> level_a_results = integrator.integrate_level_a(envelope)
    >>> level_b_results = integrator.integrate_level_b(envelope)
"""

# Import the main integration coordinator
from .bvp_integration_coordinator import BVPLevelIntegrator

# Re-export for backward compatibility
__all__ = ["BVPLevelIntegrator"]
