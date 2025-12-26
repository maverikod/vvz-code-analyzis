"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Levels integration package for BVP framework.

This package provides integration between the BVP framework and all levels
A-G of the 7D phase field theory, ensuring unified operation and
consistent data flow across all system components.

Physical Meaning:
    Provides unified integration interface between BVP framework and
    all levels of the 7D theory, ensuring that BVP serves as the
    central backbone for all system operations.

Mathematical Foundation:
    Implements integration protocols that maintain physical consistency
    and mathematical rigor across all levels while providing appropriate
    data transformations for each level's specific requirements.

Example:
    >>> from bhlff.models.levels import BVPLevelIntegrator
    >>> integrator = BVPLevelIntegrator(bvp_core)
    >>> results = integrator.integrate_all_levels(envelope)
"""

from .bvp_integration import BVPLevelIntegrator

__all__ = ["BVPLevelIntegrator"]
