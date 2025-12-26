"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Reporting package for automated testing system.

This package provides comprehensive reporting capabilities for the
7D phase field theory validation framework.

Theoretical Background:
    The reporting system combines technical metrics with physical
    interpretation to provide insights into experimental validation
    progress and adherence to 7D theory principles.

Example:
    >>> from bhlff.testing.reporting import AutomatedReportingSystem
    >>> system = AutomatedReportingSystem(config, interpreter)
"""

from .base import DailyReport, WeeklyReport, MonthlyReport, ReportType, ReportFormat
from .physics_interpreter import PhysicsInterpreter
from .template_engine import TemplateEngine
from .data_aggregator import DataAggregator
from .distribution_manager import DistributionManager

__all__ = [
    "DailyReport",
    "WeeklyReport",
    "MonthlyReport",
    "ReportType",
    "ReportFormat",
    "PhysicsInterpreter",
    "TemplateEngine",
    "DataAggregator",
    "DistributionManager",
]
