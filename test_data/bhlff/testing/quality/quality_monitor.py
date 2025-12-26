"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quality monitoring system for 7D phase field theory experiments.

This module implements comprehensive quality monitoring that tracks both
numerical accuracy and physical validity of experimental results.
"""

import logging
import numpy as np
from typing import Dict, List, Any

from .base import (
    QualityMetrics,
    QualityStatus,
    DegradationReport,
    AlertSeverity,
    QualityAlert,
)
from .physics_constraints import PhysicsConstraints
from .metric_history import MetricHistory
from .trend_analyzer import TrendAnalyzer
from .alert_system import AlertSystem
from ..automated_testing import TestResults


class QualityMonitor:
    """
    Quality monitoring system for 7D phase field theory experiments.

    Physical Meaning:
        Monitors both numerical accuracy and physical validity of
        experimental results, ensuring adherence to 7D theory principles
        and detecting deviations from expected physical behavior.

    Mathematical Foundation:
        Tracks key physical quantities:
        - Energy conservation: |dE/dt| < ε_energy
        - Virial conditions: |dE/dλ|λ=1| < ε_virial
        - Topological charge: |dB/dt| < ε_topology
        - Passivity: Re Y(ω) ≥ 0 for all ω
    """

    def __init__(
        self, baseline_metrics: Dict[str, Any], physics_constraints: PhysicsConstraints
    ):
        """
        Initialize quality monitor with physics-aware baselines.

        Physical Meaning:
            Sets up monitoring with baseline values derived from
            theoretical predictions and validated experimental results.

        Args:
            baseline_metrics (Dict[str, Any]): Baseline quality metrics.
            physics_constraints (PhysicsConstraints): Physical constraint definitions.
        """
        self.baseline_metrics = baseline_metrics
        self.physics_constraints = physics_constraints
        self.metric_history = MetricHistory()
        self.alert_system = AlertSystem({})
        self.trend_analyzer = TrendAnalyzer()
        self.logger = logging.getLogger(__name__)

    def check_quality_metrics(self, test_results: TestResults) -> QualityMetrics:
        """
        Check quality metrics against physics constraints.

        Physical Meaning:
            Validates experimental results against physical principles
            of 7D theory, checking energy conservation, topological
            invariants, and spectral properties.

        Args:
            test_results (TestResults): Results from test execution.

        Returns:
            QualityMetrics: Comprehensive quality evaluation.
        """
        quality_metrics = QualityMetrics()

        # Physics-based quality checks
        physics_quality = self._check_physics_metrics(test_results)
        quality_metrics.energy_conservation = physics_quality.get(
            "energy_conservation", 0.0
        )
        quality_metrics.virial_conditions = physics_quality.get(
            "virial_conditions", 0.0
        )
        quality_metrics.topological_charge = physics_quality.get(
            "topological_charge", 0.0
        )
        quality_metrics.passivity = physics_quality.get("passivity", 0.0)

        # Numerical quality checks
        numerical_quality = self._check_numerical_metrics(test_results)
        quality_metrics.convergence_rate = numerical_quality.get(
            "convergence_rate", 0.0
        )
        quality_metrics.accuracy = numerical_quality.get("accuracy", 0.0)
        quality_metrics.stability = numerical_quality.get("stability", 0.0)

        # Spectral quality checks
        spectral_quality = self._check_spectral_metrics(test_results)
        quality_metrics.peak_accuracy = spectral_quality.get("peak_accuracy", 0.0)
        quality_metrics.quality_factor = spectral_quality.get("quality_factor", 0.0)
        quality_metrics.abcd_accuracy = spectral_quality.get("abcd_accuracy", 0.0)

        # Overall quality score
        overall_score = self._compute_overall_quality_score(quality_metrics)
        quality_metrics.overall_score = overall_score
        quality_metrics.status = self._determine_quality_status(overall_score)

        # Store in history
        self.metric_history.add_metrics(quality_metrics)

        return quality_metrics

    def detect_quality_degradation(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: List[Dict[str, float]],
    ) -> DegradationReport:
        """
        Detect quality degradation with physics-aware analysis.

        Physical Meaning:
            Identifies degradation in physical quantities that could
            indicate violations of conservation laws or theoretical principles.

        Args:
            current_metrics (Dict[str, float]): Current quality metrics.
            historical_metrics (List[Dict[str, float]]): Historical metric values.

        Returns:
            DegradationReport: Analysis of quality degradation.
        """
        report = DegradationReport()

        # Physics-based degradation detection
        physics_degradation = self._detect_physics_degradation(
            current_metrics, historical_metrics
        )
        report.add_physics_degradation(physics_degradation)

        # Numerical degradation detection
        numerical_degradation = self._detect_numerical_degradation(
            current_metrics, historical_metrics
        )
        report.add_numerical_degradation(numerical_degradation)

        # Spectral degradation detection
        spectral_degradation = self._detect_spectral_degradation(
            current_metrics, historical_metrics
        )
        report.add_spectral_degradation(spectral_degradation)

        # Convergence degradation detection
        convergence_degradation = self._detect_convergence_degradation(
            current_metrics, historical_metrics
        )
        report.add_convergence_degradation(convergence_degradation)

        # Overall severity assessment
        severity = self._assess_degradation_severity(report)
        report.set_overall_severity(severity)

        return report

    def generate_quality_alerts(
        self, degraded_metrics: DegradationReport
    ) -> List[QualityAlert]:
        """
        Generate quality alerts with physics context.

        Physical Meaning:
            Creates alerts for quality degradation with specific
            physical interpretation and recommended actions.

        Args:
            degraded_metrics (DegradationReport): Degradation analysis.

        Returns:
            List[QualityAlert]: Generated alerts with physics context.
        """
        return self.alert_system.generate_alerts(degraded_metrics)

    def update_baseline_metrics(self, new_metrics: Dict[str, Any]) -> None:
        """
        Update baseline metrics with physics validation.

        Physical Meaning:
            Updates baseline values only if they maintain physical
            validity and improve upon existing baselines.

        Args:
            new_metrics (Dict[str, Any]): New metric values to consider.
        """
        # Validate new metrics against physics constraints
        if self.physics_constraints.validate_metrics(new_metrics):
            # Update baselines if improvement is significant
            if self._is_significant_improvement(new_metrics):
                self.baseline_metrics.update(new_metrics)
                self.logger.info("Baseline metrics updated with physics validation")
        else:
            self.logger.warning(
                "New metrics failed physics validation, not updating baselines"
            )

    def _check_physics_metrics(self, test_results: TestResults) -> Dict[str, float]:
        """Check physics-based quality metrics."""
        physics_metrics = {}

        # Calculate energy conservation score
        energy_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                energy_validation = test_result.physics_validation.get(
                    "energy_conservation", {}
                )
                energy_error = energy_validation.get("relative_error", 1.0)
                energy_score = max(
                    0.0, 1.0 - energy_error / self.physics_constraints.energy_tolerance
                )
                energy_scores.append(energy_score)

        physics_metrics["energy_conservation"] = (
            np.mean(energy_scores) if energy_scores else 0.0
        )

        # Calculate virial conditions score
        virial_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                virial_validation = test_result.physics_validation.get(
                    "virial_conditions", {}
                )
                virial_error = virial_validation.get("relative_error", 1.0)
                virial_score = max(
                    0.0, 1.0 - virial_error / self.physics_constraints.virial_tolerance
                )
                virial_scores.append(virial_score)

        physics_metrics["virial_conditions"] = (
            np.mean(virial_scores) if virial_scores else 0.0
        )

        # Calculate topological charge score
        topology_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                topology_validation = test_result.physics_validation.get(
                    "topological_charge", {}
                )
                topology_error = topology_validation.get("relative_error", 1.0)
                topology_score = max(
                    0.0,
                    1.0 - topology_error / self.physics_constraints.topology_tolerance,
                )
                topology_scores.append(topology_score)

        physics_metrics["topological_charge"] = (
            np.mean(topology_scores) if topology_scores else 0.0
        )

        # Calculate passivity score
        passivity_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                passivity_validation = test_result.physics_validation.get(
                    "passivity", {}
                )
                min_real_part = passivity_validation.get("min_real_part", -1.0)
                passivity_score = max(
                    0.0,
                    min(
                        1.0,
                        (min_real_part + self.physics_constraints.passivity_tolerance)
                        / self.physics_constraints.passivity_tolerance,
                    ),
                )
                passivity_scores.append(passivity_score)

        physics_metrics["passivity"] = (
            np.mean(passivity_scores) if passivity_scores else 0.0
        )

        return physics_metrics

    def _check_numerical_metrics(self, test_results: TestResults) -> Dict[str, float]:
        """Check numerical quality metrics."""
        numerical_metrics = {}

        # Calculate convergence rate
        convergence_rates = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                convergence_rate = numerical_metrics_data.get("convergence_rate", 0.0)
                convergence_rates.append(convergence_rate)

        numerical_metrics["convergence_rate"] = (
            np.mean(convergence_rates) if convergence_rates else 0.0
        )

        # Calculate accuracy
        accuracy_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                accuracy = numerical_metrics_data.get("accuracy", 0.0)
                accuracy_scores.append(accuracy)

        numerical_metrics["accuracy"] = (
            np.mean(accuracy_scores) if accuracy_scores else 0.0
        )

        # Calculate stability
        stability_scores = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                stability = numerical_metrics_data.get("stability", 0.0)
                stability_scores.append(stability)

        numerical_metrics["stability"] = (
            np.mean(stability_scores) if stability_scores else 0.0
        )

        return numerical_metrics

    def _check_spectral_metrics(self, test_results: TestResults) -> Dict[str, float]:
        """Check spectral quality metrics."""
        spectral_metrics = {}

        # Calculate peak accuracy
        peak_accuracies = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                peak_accuracy = numerical_metrics_data.get("peak_accuracy", 0.0)
                peak_accuracies.append(peak_accuracy)

        spectral_metrics["peak_accuracy"] = (
            np.mean(peak_accuracies) if peak_accuracies else 0.0
        )

        # Calculate quality factor
        quality_factors = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                quality_factor = numerical_metrics_data.get("quality_factor", 0.0)
                quality_factors.append(quality_factor)

        spectral_metrics["quality_factor"] = (
            np.mean(quality_factors) if quality_factors else 0.0
        )

        # Calculate ABCD accuracy
        abcd_accuracies = []
        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                numerical_metrics_data = test_result.numerical_metrics
                abcd_accuracy = numerical_metrics_data.get("abcd_accuracy", 0.0)
                abcd_accuracies.append(abcd_accuracy)

        spectral_metrics["abcd_accuracy"] = (
            np.mean(abcd_accuracies) if abcd_accuracies else 0.0
        )

        return spectral_metrics

    def _compute_overall_quality_score(self, quality_metrics: QualityMetrics) -> float:
        """Compute overall quality score."""
        # Weight different metrics by importance
        weights = {
            "energy_conservation": 0.25,
            "virial_conditions": 0.20,
            "topological_charge": 0.20,
            "passivity": 0.15,
            "convergence_rate": 0.10,
            "accuracy": 0.05,
            "stability": 0.05,
        }

        weighted_score = 0.0
        total_weight = 0.0

        for metric, weight in weights.items():
            if hasattr(quality_metrics, metric):
                value = getattr(quality_metrics, metric)
                weighted_score += value * weight
                total_weight += weight

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def _determine_quality_status(self, overall_score: float) -> QualityStatus:
        """Determine quality status from overall score."""
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

    def _detect_physics_degradation(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Detect physics-specific degradation."""
        degradation = {}

        # Check energy conservation degradation
        if "energy_conservation" in current_metrics:
            current_energy = current_metrics["energy_conservation"]
            baseline_energy = self.baseline_metrics.get("energy_conservation", 1.0)

            if current_energy < baseline_energy * 0.9:  # 10% degradation
                degradation["energy_conservation"] = {
                    "current_value": current_energy,
                    "baseline_value": baseline_energy,
                    "degradation_percent": (baseline_energy - current_energy)
                    / baseline_energy
                    * 100,
                    "severity": (
                        "high" if current_energy < baseline_energy * 0.8 else "medium"
                    ),
                }

        return degradation

    def _detect_numerical_degradation(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Detect numerical accuracy degradation."""
        degradation = {}

        # Check convergence rate degradation
        if "convergence_rate" in current_metrics:
            current_convergence = current_metrics["convergence_rate"]
            baseline_convergence = self.baseline_metrics.get("convergence_rate", 1.0)

            if current_convergence < baseline_convergence * 0.9:
                degradation["convergence_rate"] = {
                    "current_value": current_convergence,
                    "baseline_value": baseline_convergence,
                    "degradation_percent": (baseline_convergence - current_convergence)
                    / baseline_convergence
                    * 100,
                    "severity": (
                        "high"
                        if current_convergence < baseline_convergence * 0.8
                        else "medium"
                    ),
                }

        return degradation

    def _detect_spectral_degradation(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Detect spectral quality degradation."""
        degradation = {}

        # Check peak accuracy degradation
        if "peak_accuracy" in current_metrics:
            current_peak = current_metrics["peak_accuracy"]
            baseline_peak = self.baseline_metrics.get("peak_accuracy", 1.0)

            if current_peak < baseline_peak * 0.9:
                degradation["peak_accuracy"] = {
                    "current_value": current_peak,
                    "baseline_value": baseline_peak,
                    "degradation_percent": (baseline_peak - current_peak)
                    / baseline_peak
                    * 100,
                    "severity": (
                        "high" if current_peak < baseline_peak * 0.8 else "medium"
                    ),
                }

        return degradation

    def _detect_convergence_degradation(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Detect convergence quality degradation."""
        degradation = {}

        # Check overall convergence degradation
        convergence_metrics = ["convergence_rate", "accuracy", "stability"]
        convergence_scores = [
            current_metrics.get(metric, 0.0) for metric in convergence_metrics
        ]
        overall_convergence = np.mean(convergence_scores)

        baseline_convergence = np.mean(
            [self.baseline_metrics.get(metric, 1.0) for metric in convergence_metrics]
        )

        if overall_convergence < baseline_convergence * 0.9:
            degradation["overall_convergence"] = {
                "current_value": overall_convergence,
                "baseline_value": baseline_convergence,
                "degradation_percent": (baseline_convergence - overall_convergence)
                / baseline_convergence
                * 100,
                "severity": (
                    "high"
                    if overall_convergence < baseline_convergence * 0.8
                    else "medium"
                ),
            }

        return degradation

    def _assess_degradation_severity(self, report: DegradationReport) -> AlertSeverity:
        """Assess overall degradation severity."""
        severities = []

        # Collect severities from all degradation types
        for degradation_dict in [
            report.physics_degradation,
            report.numerical_degradation,
            report.spectral_degradation,
            report.convergence_degradation,
        ]:
            for degradation in degradation_dict.values():
                if isinstance(degradation, dict) and "severity" in degradation:
                    severities.append(degradation["severity"])

        if not severities:
            return AlertSeverity.LOW

        # Determine overall severity
        if "critical" in severities:
            return AlertSeverity.CRITICAL
        elif "high" in severities:
            return AlertSeverity.HIGH
        elif "medium" in severities:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW

    def _is_significant_improvement(self, new_metrics: Dict[str, Any]) -> bool:
        """Check if new metrics represent significant improvement."""
        improvement_threshold = 0.05  # 5% improvement

        for metric_name, new_value in new_metrics.items():
            if metric_name in self.baseline_metrics:
                baseline_value = self.baseline_metrics[metric_name]
                improvement = (new_value - baseline_value) / baseline_value
                if improvement > improvement_threshold:
                    return True

        return False
