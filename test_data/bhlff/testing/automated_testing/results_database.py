"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Results database for automated testing system in 7D phase field theory.

This module implements database for storing test results, providing
persistent storage and retrieval of test execution results.

Theoretical Background:
    Provides persistent storage for test results ensuring
    traceability and analysis of 7D phase field theory experiments.

Mathematical Foundation:
    Implements database operations for:
    - Test result storage
    - Result retrieval by level
    - Result aggregation and analysis

Example:
    >>> database = ResultsDatabase()
    >>> database.store_result(test_result)
    >>> results = database.get_results(level="A")
"""

import logging
from typing import Dict, List, Any
from .test_results import TestResult


class ResultsDatabase:
    """Database for storing test results."""

    def __init__(self):
        """Initialize results database."""
        self.results = []

    def store_result(self, result: TestResult) -> None:
        """Store test result in database."""
        self.results.append(result)

    def get_results(self, level: str = None) -> List[TestResult]:
        """Get test results, optionally filtered by level."""
        if level:
            return [r for r in self.results if r.level == level]
        return self.results
