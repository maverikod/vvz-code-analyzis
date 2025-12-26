"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Trend analysis for quality metrics.

This module analyzes trends in quality metrics to detect degradation
patterns and predict future quality issues in 7D phase field theory experiments.

Theoretical Background:
    The trend analyzer uses statistical methods to detect patterns
    in quality metrics that could indicate degradation or improvement
    in experimental validation.

Example:
    >>> analyzer = TrendAnalyzer()
    >>> trends = analyzer.analyze_trends(historical_metrics)
"""

import logging
import numpy as np
from typing import Dict, List, Any


class TrendAnalyzer:
    """
    Trend analysis for quality metrics.

    Physical Meaning:
        Analyzes trends in quality metrics to detect degradation
        patterns and predict future quality issues in 7D phase
        field theory experiments.
    """

    def __init__(self):
        """Initialize trend analyzer."""
        self.logger = logging.getLogger(__name__)

    def analyze_trends(
        self, historical_metrics: List[Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Analyze trends in historical metrics.

        Physical Meaning:
            Analyzes trends in physical and numerical metrics
            to detect degradation patterns that could indicate
            quality issues in 7D phase field theory.

        Args:
            historical_metrics (List[Dict[str, float]]): Historical metric values.

        Returns:
            Dict[str, Any]: Trend analysis results.
        """
        trend_analysis = {
            "overall_trend": "stable",
            "degrading_metrics": [],
            "improving_metrics": [],
            "stable_metrics": [],
            "trend_scores": {},
        }

        if len(historical_metrics) < 2:
            return trend_analysis

        # Analyze each metric
        for metric_name in historical_metrics[0].keys():
            values = [m.get(metric_name, 0.0) for m in historical_metrics]
            trend_score = self._calculate_trend_score(values)
            trend_analysis["trend_scores"][metric_name] = trend_score

            if trend_score < -0.1:  # Degrading
                trend_analysis["degrading_metrics"].append(metric_name)
            elif trend_score > 0.1:  # Improving
                trend_analysis["improving_metrics"].append(metric_name)
            else:  # Stable
                trend_analysis["stable_metrics"].append(metric_name)

        # Determine overall trend
        if len(trend_analysis["degrading_metrics"]) > len(
            trend_analysis["improving_metrics"]
        ):
            trend_analysis["overall_trend"] = "degrading"
        elif len(trend_analysis["improving_metrics"]) > len(
            trend_analysis["degrading_metrics"]
        ):
            trend_analysis["overall_trend"] = "improving"
        else:
            trend_analysis["overall_trend"] = "stable"

        return trend_analysis

    def _calculate_trend_score(self, values: List[float]) -> float:
        """
        Calculate trend score for metric values.

        Physical Meaning:
            Calculates trend score indicating whether metric
            is improving (positive), degrading (negative), or
            stable (near zero).

        Args:
            values (List[float]): Historical values.

        Returns:
            float: Trend score (-1 to 1).
        """
        if len(values) < 2:
            return 0.0

        # Simple linear regression slope
        n = len(values)
        x = np.arange(n)
        y = np.array(values)

        # Calculate slope
        slope = np.polyfit(x, y, 1)[0]

        # Normalize by value range
        value_range = max(values) - min(values)
        if value_range > 0:
            normalized_slope = slope / value_range
        else:
            normalized_slope = 0.0

        return np.clip(normalized_slope, -1.0, 1.0)
