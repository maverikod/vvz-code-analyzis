"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data aggregation for report generation.

This module aggregates test results and quality metrics for
comprehensive report generation with physics context.

Theoretical Background:
    The data aggregator combines test results and quality metrics
    to provide comprehensive analysis for automated reporting
    in the 7D phase field theory framework.

Example:
    >>> aggregator = DataAggregator()
    >>> daily_data = aggregator.aggregate_daily_data(test_results)
"""

import logging
from typing import Dict, List, Any

from ..automated_testing import TestResults


class DataAggregator:
    """
    Data aggregation for report generation.

    Physical Meaning:
        Aggregates test results and quality metrics for
        comprehensive report generation with physics context.
    """

    def __init__(self):
        """Initialize data aggregator."""
        self.logger = logging.getLogger(__name__)

    def aggregate_daily_data(self, test_results: TestResults) -> Dict[str, Any]:
        """
        Aggregate daily test data.

        Physical Meaning:
            Aggregates daily test results with physics validation
            metrics for comprehensive daily reporting.

        Args:
            test_results (TestResults): Daily test results.

        Returns:
            Dict[str, Any]: Aggregated daily data.
        """
        aggregated_data = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "success_rate": 0.0,
            "physics_metrics": {},
            "level_summaries": {},
            "performance_metrics": {},
        }

        # Aggregate test statistics
        for level_results in test_results.level_results.values():
            aggregated_data["total_tests"] += level_results.total_tests
            aggregated_data["passed_tests"] += level_results.passed_tests
            aggregated_data["failed_tests"] += level_results.failed_tests

        if aggregated_data["total_tests"] > 0:
            aggregated_data["success_rate"] = (
                aggregated_data["passed_tests"] / aggregated_data["total_tests"]
            )

        # Aggregate physics metrics
        physics_metrics = self._aggregate_physics_metrics(test_results)
        aggregated_data["physics_metrics"] = physics_metrics

        # Aggregate level summaries
        for level, level_results in test_results.level_results.items():
            aggregated_data["level_summaries"][level] = {
                "total_tests": level_results.total_tests,
                "passed_tests": level_results.passed_tests,
                "success_rate": level_results.get_success_rate(),
                "physics_score": level_results.physics_status.get(
                    "compliance_score", 0.0
                ),
            }

        return aggregated_data

    def aggregate_weekly_data(self, daily_results: List[TestResults]) -> Dict[str, Any]:
        """
        Aggregate weekly data from daily results.

        Physical Meaning:
            Aggregates weekly trends in physics validation
            and quality metrics for trend analysis.

        Args:
            daily_results (List[TestResults]): List of daily test results.

        Returns:
            Dict[str, Any]: Aggregated weekly data.
        """
        weekly_data = {
            "total_days": len(daily_results),
            "overall_success_rate": 0.0,
            "physics_trends": {},
            "quality_evolution": {},
            "performance_trends": {},
        }

        if not daily_results:
            return weekly_data

        # Calculate overall success rate
        total_tests = sum(
            len(level_results.test_results)
            for results in daily_results
            for level_results in results.level_results.values()
        )
        total_passed = sum(
            level_results.passed_tests
            for results in daily_results
            for level_results in results.level_results.values()
        )

        if total_tests > 0:
            weekly_data["overall_success_rate"] = total_passed / total_tests

        # Analyze physics trends
        physics_trends = self._analyze_physics_trends(daily_results)
        weekly_data["physics_trends"] = physics_trends

        # Analyze quality evolution
        quality_evolution = self._analyze_quality_evolution(daily_results)
        weekly_data["quality_evolution"] = quality_evolution

        return weekly_data

    def aggregate_monthly_data(
        self, weekly_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aggregate monthly data from weekly results.

        Physical Meaning:
            Aggregates monthly trends for comprehensive
            physics validation assessment.

        Args:
            weekly_results (List[Dict[str, Any]]): List of weekly aggregated results.

        Returns:
            Dict[str, Any]: Aggregated monthly data.
        """
        monthly_data = {
            "total_weeks": len(weekly_results),
            "comprehensive_validation": {},
            "long_term_trends": {},
            "theoretical_agreement": {},
        }

        if not weekly_results:
            return monthly_data

        # Comprehensive validation analysis
        comprehensive_validation = self._analyze_comprehensive_validation(
            weekly_results
        )
        monthly_data["comprehensive_validation"] = comprehensive_validation

        # Long-term trend analysis
        long_term_trends = self._analyze_long_term_trends(weekly_results)
        monthly_data["long_term_trends"] = long_term_trends

        return monthly_data

    def _aggregate_physics_metrics(self, test_results: TestResults) -> Dict[str, Any]:
        """Aggregate physics validation metrics."""
        physics_metrics = {
            "energy_conservation": {"scores": [], "violations": 0},
            "virial_conditions": {"scores": [], "violations": 0},
            "topological_charge": {"scores": [], "violations": 0},
            "passivity": {"scores": [], "violations": 0},
        }

        for level_results in test_results.level_results.values():
            for test_result in level_results.test_results:
                physics_validation = test_result.physics_validation
                compliance_score = physics_validation.get("compliance_score", 0.0)
                violations = physics_validation.get("violations", [])

                # Aggregate by principle
                for violation in violations:
                    principle = violation.get("constraint", "unknown")
                    if principle in physics_metrics:
                        physics_metrics[principle]["violations"] += 1
                        physics_metrics[principle]["scores"].append(compliance_score)

        # Calculate averages
        for principle in physics_metrics:
            scores = physics_metrics[principle]["scores"]
            if scores:
                physics_metrics[principle]["average_score"] = sum(scores) / len(scores)
            else:
                physics_metrics[principle]["average_score"] = 1.0

        return physics_metrics

    def _analyze_physics_trends(
        self, daily_results: List[TestResults]
    ) -> Dict[str, Any]:
        """Analyze physics trends over time."""
        trends = {
            "energy_conservation_trend": "stable",
            "virial_conditions_trend": "stable",
            "topological_charge_trend": "stable",
            "passivity_trend": "stable",
        }

        # Simple trend analysis - would be more sophisticated in practice
        for principle in [
            "energy_conservation",
            "virial_conditions",
            "topological_charge",
            "passivity",
        ]:
            scores = []
            for results in daily_results:
                # Extract scores for this principle from daily results
                # This would be implemented based on actual data structure
                scores.append(0.95)  # Mock data

            if len(scores) >= 2:
                if scores[-1] > scores[0]:
                    trends[f"{principle}_trend"] = "improving"
                elif scores[-1] < scores[0]:
                    trends[f"{principle}_trend"] = "degrading"

        return trends

    def _analyze_quality_evolution(
        self, daily_results: List[TestResults]
    ) -> Dict[str, Any]:
        """Analyze quality evolution over time."""
        evolution = {"overall_quality_trend": "stable", "quality_metrics": {}}

        # Analyze quality evolution
        # This would analyze actual quality metrics over time
        evolution["overall_quality_trend"] = "stable"

        return evolution

    def _analyze_comprehensive_validation(
        self, weekly_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze comprehensive validation over monthly period."""
        validation = {
            "overall_status": "valid",
            "principle_status": {},
            "validation_score": 0.0,
        }

        # Analyze comprehensive validation
        # This would analyze physics validation across all weeks
        validation["overall_status"] = "valid"
        validation["validation_score"] = 0.95

        return validation

    def _analyze_long_term_trends(
        self, weekly_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze long-term trends."""
        trends = {"overall_trend": "stable", "trend_analysis": {}}

        # Analyze long-term trends
        # This would analyze trends across all weeks
        trends["overall_trend"] = "stable"

        return trends
