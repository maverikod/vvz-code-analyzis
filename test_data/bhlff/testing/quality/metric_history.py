"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Historical tracking of quality metrics.

This module maintains historical record of quality metrics for trend
analysis and degradation detection in 7D phase field theory.

Theoretical Background:
    The metric history system tracks quality metrics over time to
    detect trends, degradation patterns, and predict future issues
    in experimental validation.

Example:
    >>> history = MetricHistory(max_history=1000)
    >>> history.add_metrics(metrics)
    >>> recent = history.get_recent_metrics(days=7)
"""

import logging
from datetime import datetime, timedelta
from typing import List
from collections import deque

from .base import QualityMetrics


class MetricHistory:
    """
    Historical tracking of quality metrics.

    Physical Meaning:
        Maintains historical record of quality metrics for trend
        analysis and degradation detection in 7D phase field theory.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize metric history.

        Physical Meaning:
            Sets up historical tracking with appropriate retention
            period for trend analysis.

        Args:
            max_history (int): Maximum number of historical records.
        """
        self.max_history = max_history
        self.metrics_history = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)

    def add_metrics(self, metrics: QualityMetrics) -> None:
        """
        Add metrics to history.

        Physical Meaning:
            Records quality metrics for historical analysis
            and trend detection.

        Args:
            metrics (QualityMetrics): Quality metrics to record.
        """
        self.metrics_history.append(metrics)
        self.timestamps.append(metrics.timestamp)

    def get_recent_metrics(self, days: int = 7) -> List[QualityMetrics]:
        """
        Get recent metrics within specified time window.

        Physical Meaning:
            Retrieves recent quality metrics for trend analysis
            and degradation detection.

        Args:
            days (int): Number of days to look back.

        Returns:
            List[QualityMetrics]: Recent metrics within time window.
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        recent_metrics = []

        for i, timestamp in enumerate(self.timestamps):
            if timestamp >= cutoff_time:
                recent_metrics.append(self.metrics_history[i])

        return recent_metrics

    def get_trend_data(self, metric_name: str, days: int = 30) -> List[float]:
        """
        Get trend data for specific metric.

        Physical Meaning:
            Extracts historical values for specific metric to
            analyze trends and detect degradation.

        Args:
            metric_name (str): Name of metric to analyze.
            days (int): Number of days to analyze.

        Returns:
            List[float]: Historical values for the metric.
        """
        recent_metrics = self.get_recent_metrics(days)
        trend_data = []

        for metrics in recent_metrics:
            if hasattr(metrics, metric_name):
                trend_data.append(getattr(metrics, metric_name))

        return trend_data
