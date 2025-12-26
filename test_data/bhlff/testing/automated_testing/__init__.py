"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Automated testing system package for 7D phase field theory experiments.

This package implements comprehensive automated testing system that orchestrates
testing of all experimental levels (A-G) with physics-first prioritization,
ensuring validation of 7D theory principles including phase field dynamics,
topological invariants, and energy conservation.

Theoretical Background:
    Implements systematic validation of:
    - Fractional Laplacian operators: (-Δ)^β
    - Energy conservation: dE/dt = 0
    - Virial conditions: dE/dλ|λ=1 = 0
    - Topological charge conservation: dB/dt = 0

Example:
    >>> from .automated_testing_system import AutomatedTestingSystem
    >>> testing_system = AutomatedTestingSystem(config_path, physics_validator)
    >>> results = testing_system.run_all_tests(levels=["A", "B", "C"])
"""

from .automated_testing_system import AutomatedTestingSystem
from .physics_validator import PhysicsValidator
from .test_scheduler import TestScheduler
from .resource_manager import ResourceManager, ResourceContext, ResourceLimitError
from .results_database import ResultsDatabase
from .test_results import (
    TestResult,
    LevelTestResults,
    TestResults,
    TestPriority,
    TestStatus,
)

__all__ = [
    "AutomatedTestingSystem",
    "PhysicsValidator",
    "TestScheduler",
    "ResourceManager",
    "ResourceContext",
    "ResourceLimitError",
    "ResultsDatabase",
    "TestResult",
    "LevelTestResults",
    "TestResults",
    "TestPriority",
    "TestStatus",
]
