"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level E experiments for solitons and topological defects.

This module implements comprehensive stability and sensitivity analysis
of the 7D phase field theory, investigating the robustness of solitons
and topological defects under various conditions.

Theoretical Background:
    Level E focuses on solitons and topological defects in the 7D phase
    field theory, representing fundamental particle-like structures with
    topological protection. These structures emerge as stable localized
    solutions of nonlinear field equations with non-trivial winding numbers.

Key Components:
    - Soliton models: Baryon and Skyrmion solitons with topological charge
    - Defect models: Topological defects with winding numbers
    - Sensitivity analysis: Sobol indices for parameter ranking
    - Robustness testing: Stability under perturbations
    - Phase mapping: Classification of system behavior regimes

Example:
    >>> from bhlff.models.level_e import LevelEExperiments
    >>> experiments = LevelEExperiments(config)
    >>> results = experiments.run_full_analysis()
"""

from .sensitivity_analysis import SensitivityAnalyzer
from .robustness_tests import RobustnessTester
from .discretization_effects import DiscretizationAnalyzer
from .failure_detection import FailureDetector
from .phase_mapping import PhaseMapper
from .performance_analysis import PerformanceAnalyzer
from .soliton_models import SolitonModel, BaryonSoliton, SkyrmionSoliton
from .defect_models import DefectModel, VortexDefect, MultiDefectSystem
from .level_e_experiments import LevelEExperiments

__all__ = [
    "SensitivityAnalyzer",
    "RobustnessTester",
    "DiscretizationAnalyzer",
    "FailureDetector",
    "PhaseMapper",
    "PerformanceAnalyzer",
    "SolitonModel",
    "BaryonSoliton",
    "SkyrmionSoliton",
    "DefectModel",
    "VortexDefect",
    "MultiDefectSystem",
    "LevelEExperiments",
]
