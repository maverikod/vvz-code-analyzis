"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base classes and enumerations for quality monitoring system.

This module provides the fundamental data structures and enumerations
for the quality monitoring system in the 7D phase field theory framework.

Theoretical Background:
    The quality monitoring system tracks key physical quantities:
    - Energy conservation: |dE/dt| < ε_energy
    - Virial conditions: |dE/dλ|λ=1| < ε_virial
    - Topological charge: |dB/dt| < ε_topology
    - Passivity: Re Y(ω) ≥ 0 for all ω

Example:
    >>> metrics = QualityMetrics()
    >>> alert = QualityAlert("energy_conservation", AlertSeverity.HIGH)
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class QualityStatus(Enum):
    """Quality assessment status."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QualityMetrics:
    """Quality metrics container."""

    energy_conservation: float = 0.0
    virial_conditions: float = 0.0
    topological_charge: float = 0.0
    passivity: float = 0.0
    numerical_accuracy: float = 0.0
    convergence_rate: float = 0.0
    stability_indicators: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def get_overall_score(self) -> float:
        """Get overall quality score."""
        scores = [
            self.energy_conservation,
            self.virial_conditions,
            self.topological_charge,
            self.passivity,
            self.numerical_accuracy,
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def get_status(self) -> QualityStatus:
        """Get quality status based on scores."""
        overall_score = self.get_overall_score()
        if overall_score >= 0.95:
            return QualityStatus.EXCELLENT
        elif overall_score >= 0.85:
            return QualityStatus.GOOD
        elif overall_score >= 0.70:
            return QualityStatus.ACCEPTABLE
        elif overall_score >= 0.50:
            return QualityStatus.DEGRADED
        else:
            return QualityStatus.CRITICAL


@dataclass
class DegradationReport:
    """Report of quality degradation."""

    metric_name: str
    previous_value: float
    current_value: float
    degradation_percent: float
    severity: AlertSeverity
    timestamp: datetime = field(default_factory=datetime.now)
    recommendations: List[str] = field(default_factory=list)

    def get_degradation_description(self) -> str:
        """Get human-readable degradation description."""
        return f"{self.metric_name} degraded from {self.previous_value:.3f} to {self.current_value:.3f} ({self.degradation_percent:.1f}%)"


@dataclass
class QualityAlert:
    """Quality alert for monitoring system."""

    metric_name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None
    recommendations: List[str] = field(default_factory=list)

    def get_alert_summary(self) -> str:
        """Get alert summary."""
        return f"{self.severity.value.upper()}: {self.metric_name} - {self.message}"
