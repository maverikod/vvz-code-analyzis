"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Test results data structures for automated testing system in 7D phase field theory.

This module implements data structures for test execution results with physics validation,
including test results, level results, and comprehensive test results.

Theoretical Background:
    Test results capture both numerical accuracy and physical validity
    of 7D phase field theory experiments, ensuring conservation laws
    and theoretical predictions are maintained.

Mathematical Foundation:
    Implements data structures for:
    - Test execution results with physics validation
    - Level-specific test results aggregation
    - Comprehensive test results with physics status

Example:
    >>> result = TestResult(test_id="A01", test_name="Energy Conservation", level="A", status=TestStatus.PASSED, start_time=datetime.now())
    >>> level_results = LevelTestResults(level="A")
    >>> level_results.add_test_result(result)
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class TestPriority(Enum):
    """Test execution priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestStatus(Enum):
    """Test execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Test execution result with physics validation."""

    test_id: str
    test_name: str
    level: str
    status: TestStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time: Optional[float] = None
    physics_validation: Dict[str, Any] = field(default_factory=dict)
    numerical_metrics: Dict[str, float] = field(default_factory=dict)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate execution time if test completed."""
        if self.end_time and self.start_time:
            self.execution_time = (self.end_time - self.start_time).total_seconds()


@dataclass
class LevelTestResults:
    """Test results for specific experimental level."""

    level: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    test_results: List[TestResult] = field(default_factory=list)
    physics_status: Dict[str, Any] = field(default_factory=dict)
    quality_metrics: Dict[str, float] = field(default_factory=dict)
    execution_time: float = 0.0

    def add_test_result(self, result: TestResult) -> None:
        """Add test result to level results."""
        self.test_results.append(result)
        self.total_tests += 1

        if result.status == TestStatus.PASSED:
            self.passed_tests += 1
        elif result.status == TestStatus.FAILED:
            self.failed_tests += 1
        elif result.status == TestStatus.SKIPPED:
            self.skipped_tests += 1
        elif result.status == TestStatus.ERROR:
            self.error_tests += 1

    def has_critical_physics_failures(self) -> bool:
        """Check if level has critical physics validation failures."""
        for result in self.test_results:
            if result.status == TestStatus.FAILED:
                physics_violations = result.physics_validation.get("violations", [])
                critical_violations = [
                    v for v in physics_violations if v.get("severity") == "critical"
                ]
                if critical_violations:
                    return True
        return False

    def get_success_rate(self) -> float:
        """Calculate success rate for level."""
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests


@dataclass
class TestResults:
    """Comprehensive test execution results."""

    start_time: datetime
    end_time: Optional[datetime] = None
    total_execution_time: Optional[float] = None
    level_results: Dict[str, LevelTestResults] = field(default_factory=dict)
    overall_success_rate: float = 0.0
    physics_validation_summary: Dict[str, Any] = field(default_factory=dict)
    quality_summary: Dict[str, Any] = field(default_factory=dict)
    performance_summary: Dict[str, Any] = field(default_factory=dict)

    def add_level_results(self, level: str, results: LevelTestResults) -> None:
        """Add level results to overall results."""
        self.level_results[level] = results

    def calculate_overall_metrics(self) -> None:
        """Calculate overall metrics from level results."""
        if self.end_time and self.start_time:
            self.total_execution_time = (
                self.end_time - self.start_time
            ).total_seconds()

        total_tests = sum(level.total_tests for level in self.level_results.values())
        total_passed = sum(level.passed_tests for level in self.level_results.values())

        if total_tests > 0:
            self.overall_success_rate = total_passed / total_tests
