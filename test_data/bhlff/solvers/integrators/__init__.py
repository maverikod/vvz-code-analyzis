"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Time integrators package.

This package provides time integration methods for solving time-dependent
phase field equations in the BHLFF framework.

Physical Meaning:
    Time integrators implement numerical methods for advancing phase field
    configurations in time, handling the temporal evolution of the system.

Mathematical Foundation:
    Implements various time integration schemes including explicit, implicit,
    and adaptive methods for solving time-dependent phase field equations.
"""

from .time_integrator import TimeIntegrator
from .bvp_modulation_integrator import BVPModulationIntegrator

__all__ = [
    "TimeIntegrator",
    "BVPModulationIntegrator",
]
