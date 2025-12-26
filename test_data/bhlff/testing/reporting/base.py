"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base classes and enumerations for automated reporting system.

This module provides the fundamental data structures and enumerations
for the automated reporting system in the 7D phase field theory framework.

Theoretical Background:
    The reporting system provides comprehensive analysis of experimental
    validation progress, combining technical metrics with physical
    interpretation for 7D theory validation.

Example:
    >>> report = DailyReport(datetime.now())
    >>> report.set_physics_summary(summary_data)
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..quality_monitor import QualityAlert


class ReportType(Enum):
    """Report type enumeration."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportFormat(Enum):
    """Report format enumeration."""

    PDF = "pdf"
    HTML = "html"
    JSON = "json"
    TEXT = "text"


@dataclass
class DailyReport:
    """Daily test execution report."""

    date: datetime
    physics_summary: Dict[str, Any] = field(default_factory=dict)
    level_analysis: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    quality_summary: Dict[str, Any] = field(default_factory=dict)
    performance_summary: Dict[str, Any] = field(default_factory=dict)
    validation_status: Dict[str, Any] = field(default_factory=dict)
    alerts: List[QualityAlert] = field(default_factory=list)

    def set_physics_summary(self, summary: Dict[str, Any]) -> None:
        """Set physics validation summary."""
        self.physics_summary = summary

    def add_level_analysis(self, level: str, analysis: Dict[str, Any]) -> None:
        """Add level-specific analysis."""
        self.level_analysis[level] = analysis

    def set_quality_summary(self, summary: Dict[str, Any]) -> None:
        """Set quality metrics summary."""
        self.quality_summary = summary

    def set_performance_summary(self, summary: Dict[str, Any]) -> None:
        """Set performance metrics summary."""
        self.performance_summary = summary

    def set_validation_status(self, status: Dict[str, Any]) -> None:
        """Set validation status."""
        self.validation_status = status


@dataclass
class WeeklyReport:
    """Weekly aggregated report."""

    week_start: datetime
    week_end: datetime
    physics_trends: Dict[str, Any] = field(default_factory=dict)
    convergence_analysis: Dict[str, Any] = field(default_factory=dict)
    quality_evolution: Dict[str, Any] = field(default_factory=dict)
    performance_trends: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def set_physics_trends(self, trends: Dict[str, Any]) -> None:
        """Set physics trend analysis."""
        self.physics_trends = trends

    def set_convergence_analysis(self, analysis: Dict[str, Any]) -> None:
        """Set convergence analysis."""
        self.convergence_analysis = analysis

    def set_quality_evolution(self, evolution: Dict[str, Any]) -> None:
        """Set quality evolution analysis."""
        self.quality_evolution = evolution

    def set_performance_trends(self, trends: Dict[str, Any]) -> None:
        """Set performance trend analysis."""
        self.performance_trends = trends

    def set_recommendations(self, recommendations: List[str]) -> None:
        """Set recommendations."""
        self.recommendations = recommendations


@dataclass
class MonthlyReport:
    """Monthly comprehensive report."""

    month_start: datetime
    month_end: datetime
    physics_validation: Dict[str, Any] = field(default_factory=dict)
    prediction_comparison: Dict[str, Any] = field(default_factory=dict)
    long_term_trends: Dict[str, Any] = field(default_factory=dict)
    progress_assessment: Dict[str, Any] = field(default_factory=dict)
    future_recommendations: List[str] = field(default_factory=list)

    def set_physics_validation(self, validation: Dict[str, Any]) -> None:
        """Set physics validation results."""
        self.physics_validation = validation

    def set_prediction_comparison(self, comparison: Dict[str, Any]) -> None:
        """Set theoretical prediction comparison."""
        self.prediction_comparison = comparison

    def set_long_term_trends(self, trends: Dict[str, Any]) -> None:
        """Set long-term trend analysis."""
        self.long_term_trends = trends

    def set_progress_assessment(self, assessment: Dict[str, Any]) -> None:
        """Set research progress assessment."""
        self.progress_assessment = assessment

    def set_future_recommendations(self, recommendations: List[str]) -> None:
        """Set future recommendations."""
        self.future_recommendations = recommendations
