"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Alert system for quality degradation in 7D phase field theory.

This module implements an alert system that generates alerts for quality
degradation with physics-aware interpretation and recommended actions.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any

from .base import QualityAlert, AlertSeverity, DegradationReport


class AlertSystem:
    """
    Alert system for quality degradation.

    Physical Meaning:
        Generates alerts for quality degradation with physics-aware
        interpretation and recommended actions for 7D phase field theory.
    """

    def __init__(self, alert_config: Dict[str, Any]):
        """
        Initialize alert system.

        Physical Meaning:
            Sets up alert system with physics-aware thresholds
            and notification configuration.

        Args:
            alert_config (Dict[str, Any]): Alert configuration.
        """
        self.alert_config = alert_config
        self.logger = logging.getLogger(__name__)
        self.alert_history = []

    def generate_alerts(
        self, degradation_report: DegradationReport
    ) -> List[QualityAlert]:
        """
        Generate alerts for quality degradation.

        Physical Meaning:
            Creates alerts for quality degradation with specific
            physical interpretation and recommended actions.

        Args:
            degradation_report (DegradationReport): Degradation analysis.

        Returns:
            List[QualityAlert]: Generated alerts.
        """
        alerts = []

        # Physics-based alerts
        physics_alerts = self._generate_physics_alerts(
            degradation_report.physics_degradation
        )
        alerts.extend(physics_alerts)

        # Numerical alerts
        numerical_alerts = self._generate_numerical_alerts(
            degradation_report.numerical_degradation
        )
        alerts.extend(numerical_alerts)

        # Spectral alerts
        spectral_alerts = self._generate_spectral_alerts(
            degradation_report.spectral_degradation
        )
        alerts.extend(spectral_alerts)

        # Convergence alerts
        convergence_alerts = self._generate_convergence_alerts(
            degradation_report.convergence_degradation
        )
        alerts.extend(convergence_alerts)

        # Store alerts in history
        self.alert_history.extend(alerts)

        return alerts

    def _generate_physics_alerts(
        self, physics_degradation: Dict[str, Any]
    ) -> List[QualityAlert]:
        """Generate physics-specific alerts."""
        alerts = []

        # Energy conservation alert
        if physics_degradation.get("energy_conservation", {}).get(
            "severity", "none"
        ) in ["high", "critical"]:
            alert = QualityAlert(
                alert_type="energy_conservation_violation",
                severity=AlertSeverity.CRITICAL,
                timestamp=datetime.now(),
                metric_name="energy_conservation",
                current_value=physics_degradation.get("energy_conservation", {}).get(
                    "current_value", 0.0
                ),
                baseline_value=physics_degradation.get("energy_conservation", {}).get(
                    "baseline_value", 0.0
                ),
                threshold=1e-6,
                physical_interpretation="Energy conservation violation indicates potential numerical instability or physics violation",
                recommended_actions=[
                    "Check numerical solver stability",
                    "Verify energy conservation implementation",
                    "Review time step and grid resolution",
                ],
                theoretical_context="Energy conservation is fundamental to 7D phase field theory",
                mathematical_expression="|dE/dt| < ε_energy",
            )
            alerts.append(alert)

        # Virial condition alert
        if physics_degradation.get("virial_conditions", {}).get("severity", "none") in [
            "high",
            "critical",
        ]:
            alert = QualityAlert(
                alert_type="virial_condition_violation",
                severity=AlertSeverity.HIGH,
                timestamp=datetime.now(),
                metric_name="virial_conditions",
                current_value=physics_degradation.get("virial_conditions", {}).get(
                    "current_value", 0.0
                ),
                baseline_value=physics_degradation.get("virial_conditions", {}).get(
                    "baseline_value", 0.0
                ),
                threshold=1e-6,
                physical_interpretation="Virial condition violation indicates energy balance issues",
                recommended_actions=[
                    "Check energy balance calculations",
                    "Verify virial condition implementation",
                    "Review boundary conditions",
                ],
                theoretical_context="Virial conditions ensure proper energy distribution in phase fields",
                mathematical_expression="|dE/dλ|λ=1| < ε_virial",
            )
            alerts.append(alert)

        return alerts

    def _generate_numerical_alerts(
        self, numerical_degradation: Dict[str, Any]
    ) -> List[QualityAlert]:
        """Generate numerical accuracy alerts."""
        alerts = []

        # Convergence alert
        if numerical_degradation.get("convergence_rate", {}).get(
            "severity", "none"
        ) in ["medium", "high", "critical"]:
            alert = QualityAlert(
                alert_type="convergence_degradation",
                severity=AlertSeverity.MEDIUM,
                timestamp=datetime.now(),
                metric_name="convergence_rate",
                current_value=numerical_degradation.get("convergence_rate", {}).get(
                    "current_value", 0.0
                ),
                baseline_value=numerical_degradation.get("convergence_rate", {}).get(
                    "baseline_value", 0.0
                ),
                threshold=0.8,
                physical_interpretation="Convergence degradation indicates numerical accuracy issues",
                recommended_actions=[
                    "Check grid resolution",
                    "Review time step size",
                    "Verify numerical scheme stability",
                ],
                theoretical_context="Convergence is essential for accurate physical predictions",
                mathematical_expression="convergence_rate > threshold",
            )
            alerts.append(alert)

        return alerts

    def _generate_spectral_alerts(
        self, spectral_degradation: Dict[str, Any]
    ) -> List[QualityAlert]:
        """Generate spectral quality alerts."""
        alerts = []

        # Peak accuracy alert
        if spectral_degradation.get("peak_accuracy", {}).get("severity", "none") in [
            "medium",
            "high",
            "critical",
        ]:
            alert = QualityAlert(
                alert_type="spectral_peak_degradation",
                severity=AlertSeverity.MEDIUM,
                timestamp=datetime.now(),
                metric_name="peak_accuracy",
                current_value=spectral_degradation.get("peak_accuracy", {}).get(
                    "current_value", 0.0
                ),
                baseline_value=spectral_degradation.get("peak_accuracy", {}).get(
                    "baseline_value", 0.0
                ),
                threshold=0.95,
                physical_interpretation="Spectral peak degradation indicates resonance analysis issues",
                recommended_actions=[
                    "Check FFT implementation",
                    "Review spectral analysis parameters",
                    "Verify frequency resolution",
                ],
                theoretical_context="Spectral peaks are crucial for resonance analysis in 7D theory",
                mathematical_expression="peak_accuracy > threshold",
            )
            alerts.append(alert)

        return alerts

    def _generate_convergence_alerts(
        self, convergence_degradation: Dict[str, Any]
    ) -> List[QualityAlert]:
        """Generate convergence quality alerts."""
        alerts = []

        # Overall convergence alert
        if convergence_degradation.get("overall_convergence", {}).get(
            "severity", "none"
        ) in ["high", "critical"]:
            alert = QualityAlert(
                alert_type="overall_convergence_degradation",
                severity=AlertSeverity.HIGH,
                timestamp=datetime.now(),
                metric_name="overall_convergence",
                current_value=convergence_degradation.get(
                    "overall_convergence", {}
                ).get("current_value", 0.0),
                baseline_value=convergence_degradation.get(
                    "overall_convergence", {}
                ).get("baseline_value", 0.0),
                threshold=0.9,
                physical_interpretation="Overall convergence degradation indicates systematic numerical issues",
                recommended_actions=[
                    "Review numerical scheme",
                    "Check grid and time step",
                    "Verify boundary conditions",
                    "Consider adaptive refinement",
                ],
                theoretical_context="Convergence is fundamental for reliable physical predictions",
                mathematical_expression="overall_convergence > threshold",
            )
            alerts.append(alert)

        return alerts
