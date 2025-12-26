"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Test scheduler for automated testing system in 7D phase field theory.

This module implements test scheduling with physics-first prioritization,
ensuring fundamental physical principles are validated before numerical
accuracy tests.

Theoretical Background:
    Schedules tests with priority given to fundamental physical
    principles validation before numerical accuracy tests.

Mathematical Foundation:
    Implements physics-first test ordering:
    - Level A: Basic physics validation
    - Level B: Fundamental properties
    - Level C: Boundary effects
    - Level D: Multi-mode interactions
    - Level E: Solitons and defects
    - Level F: Collective effects
    - Level G: Cosmological models

Example:
    >>> scheduler = TestScheduler()
    >>> scheduler.add_test("A01", "A", TestPriority.CRITICAL, [], ["energy_conservation"])
    >>> execution_order = scheduler.get_execution_order()
"""

import logging
from typing import Dict, List, Any
from .test_results import TestPriority, TestStatus


class TestScheduler:
    """
    Test scheduler with physics-first prioritization.

    Physical Meaning:
        Schedules tests with priority given to fundamental physical
        principles validation before numerical accuracy tests.
    """

    def __init__(self):
        """Initialize test scheduler."""
        self.scheduled_tests = []
        self.test_dependencies = {}
        self.physics_priority_order = ["A", "B", "C", "D", "E", "F", "G"]

    def add_test(
        self,
        test_id: str,
        level: str,
        priority: TestPriority,
        dependencies: List[str] = None,
        physics_checks: List[str] = None,
    ) -> None:
        """
        Add test to scheduler.

        Physical Meaning:
            Adds test to scheduler with physics-aware prioritization
            and dependency management.

        Args:
            test_id (str): Unique test identifier.
            level (str): Experimental level (A-G).
            priority (TestPriority): Test priority level.
            dependencies (List[str]): Test dependencies.
            physics_checks (List[str]): Physics validation checks.
        """
        if dependencies is None:
            dependencies = []
        if physics_checks is None:
            physics_checks = []

        test_spec = {
            "test_id": test_id,
            "level": level,
            "priority": priority,
            "dependencies": dependencies,
            "physics_checks": physics_checks,
            "scheduled_time": None,
            "status": TestStatus.PENDING,
        }

        self.scheduled_tests.append(test_spec)
        self.test_dependencies[test_id] = dependencies

    def get_execution_order(self) -> List[str]:
        """
        Get test execution order with physics prioritization.

        Physical Meaning:
            Returns ordered list of test IDs with physics-first
            prioritization and dependency resolution.

        Returns:
            List[str]: Ordered list of test IDs for execution.
        """
        # Sort by physics priority order first
        level_priority = {
            level: i for i, level in enumerate(self.physics_priority_order)
        }

        # Sort by priority within levels
        priority_order = {
            TestPriority.CRITICAL: 0,
            TestPriority.HIGH: 1,
            TestPriority.MEDIUM: 2,
            TestPriority.LOW: 3,
        }

        sorted_tests = sorted(
            self.scheduled_tests,
            key=lambda t: (
                level_priority.get(t["level"], 999),
                priority_order.get(t["priority"], 999),
            ),
        )

        # Resolve dependencies
        execution_order = []
        completed_tests = set()

        for test in sorted_tests:
            test_id = test["test_id"]
            dependencies = test["dependencies"]

            # Check if all dependencies are completed
            if all(dep in completed_tests for dep in dependencies):
                execution_order.append(test_id)
                completed_tests.add(test_id)

        return execution_order
