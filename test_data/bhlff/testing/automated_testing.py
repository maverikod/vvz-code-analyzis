"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Automated testing system facade for 7D phase field theory experiments.

This module provides a facade interface for automated testing system,
delegating to specialized modules for different aspects of testing.

Theoretical Background:
    Implements systematic validation of:
    - Fractional Laplacian operators: (-Δ)^β
    - Energy conservation: dE/dt = 0
    - Virial conditions: dE/dλ|λ=1 = 0
    - Topological charge conservation: dB/dt = 0

Example:
    >>> from .automated_testing import AutomatedTestingSystem
    >>> testing_system = AutomatedTestingSystem(config_path, physics_validator)
    >>> results = testing_system.run_all_tests(levels=["A", "B", "C"])
"""

from typing import Dict, Any
from .automated_testing.automated_testing_system import AutomatedTestingSystem
from .automated_testing.physics_validator import PhysicsValidator
from .automated_testing.test_scheduler import TestScheduler
from .automated_testing.resource_manager import (
    ResourceManager,
    ResourceContext,
    ResourceLimitError,
)
from .automated_testing.results_database import ResultsDatabase
from .automated_testing.test_results import (
    TestResult,
    LevelTestResults,
    TestResults,
    TestPriority,
    TestStatus,
)

# Re-export the main classes for backward compatibility
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
