"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Defect models interface for Level E experiments in 7D phase field theory.

This module provides the main interface for topological defect models,
delegating to specialized modules for core functionality, dynamics,
interactions, and implementations.

Theoretical Background:
    Topological defects are singularities in the phase field that carry
    non-trivial winding numbers and create localized distortions in the
    field configuration. They represent fundamental structures in the
    7D theory with rich dynamics and interactions.

Mathematical Foundation:
    Implements defects with topological charge q ∈ ℤ where
    ∮∇φ·dl = 2πq around the defect core. The dynamics follows the
    Thiele equation: ẋ = -∇U_eff + G × ẋ + D ẋ.

Example:
    >>> defect = VortexDefect(domain, physics_params)
    >>> field = defect.create_defect(position, charge)
"""

# Import all defect classes and functionality
from .defect_core import DefectModel
from .defect_implementations import VortexDefect, MultiDefectSystem
from .defect_dynamics import DefectDynamics
from .defect_interactions import DefectInteractions

# Make all classes available at package level
__all__ = [
    "DefectModel",
    "VortexDefect",
    "MultiDefectSystem",
    "DefectDynamics",
    "DefectInteractions",
]
