"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Stability analysis methods for time stability analyzer.

This module provides stability analysis methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class TimeStabilityAnalysisMixin:
    """Mixin providing stability analysis methods."""
    
    def _analyze_time_step_stability(
        self, results: Dict[float, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze time step stability."""
        time_steps = sorted(results.keys())
        stability_metrics = {}
        
        for metric in self.convergence_metrics:
            if metric in results[time_steps[0]]["metrics"]:
                # Extract values for this metric
                values = [results[dt]["metrics"][metric] for dt in time_steps]
                
                # Analyze stability
                stability = self._analyze_metric_stability(time_steps, values)
                stability_metrics[metric] = stability
        
        # Overall stability analysis
        overall_stability = self._analyze_overall_stability(stability_metrics)
        
        return {
            "stability_metrics": stability_metrics,
            "overall_stability": overall_stability,
            "time_steps": time_steps,
        }
    
    def _analyze_metric_stability(
        self, time_steps: List[float], values: List[float]
    ) -> Dict[str, Any]:
        """Analyze stability of a metric with respect to time step."""
        if len(values) < 2:
            return {"stability": "insufficient_data", "score": 0.0}
        
        # Compute relative changes
        relative_changes = []
        for i in range(len(values) - 1):
            if values[i + 1] != 0:
                rel_change = abs(values[i] - values[i + 1]) / abs(values[i + 1])
                relative_changes.append(rel_change)
        
        # Assess stability
        max_change = max(relative_changes) if relative_changes else 0.0
        mean_change = np.mean(relative_changes) if relative_changes else 0.0
        
        if max_change < 0.01:
            stability = "excellent"
            score = 1.0
        elif max_change < 0.05:
            stability = "good"
            score = 0.8
        elif max_change < 0.1:
            stability = "fair"
            score = 0.6
        else:
            stability = "poor"
            score = 0.3
        
        return {
            "stability": stability,
            "score": score,
            "max_change": max_change,
            "mean_change": mean_change,
        }
    
    def _analyze_overall_stability(
        self, stability_metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze overall time step stability."""
        scores = [metrics["score"] for metrics in stability_metrics.values()]
        
        if not scores:
            return {"overall_score": 0.0, "stability": "unknown"}
        
        overall_score = np.mean(scores)
        
        if overall_score > 0.8:
            stability = "excellent"
        elif overall_score > 0.6:
            stability = "good"
        elif overall_score > 0.4:
            stability = "fair"
        else:
            stability = "poor"
        
        return {
            "overall_score": overall_score,
            "stability": stability,
            "individual_scores": {
                metric: metrics["score"]
                for metric, metrics in stability_metrics.items()
            },
        }

