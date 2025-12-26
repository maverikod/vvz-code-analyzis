"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis for failure detector.

This module provides functionality for analyzing parameter boundaries where
failures occur in the 7D phase field theory simulations.
"""

import numpy as np
from typing import Any, Dict, Tuple


class FailureDetectorBoundariesMixin:
    """Mixin providing failure boundary analysis."""
    
    def analyze_failure_boundaries(
        self, parameter_ranges: Dict[str, Tuple[float, float]]
    ) -> Dict[str, Any]:
        """
        Analyze boundaries where failures occur.
        
        Physical Meaning:
            Identifies parameter ranges where the system fails,
            establishing boundaries of applicability.
        """
        boundaries: Dict[str, Any] = {}
        
        for param_name, (min_val, max_val) in parameter_ranges.items():
            print(f"Analyzing failure boundaries for {param_name}")
            test_values = np.linspace(min_val, max_val, 20)
            failure_points = []
            
            for value in test_values:
                test_config = self.config.copy()
                test_config[param_name] = float(value)
                
                test_detector = self.__class__(test_config)
                test_failures = test_detector.detect_failures()
                
                has_failures = any(
                    result.get("detected", False)
                    for result in test_failures.values()
                    if isinstance(result, dict)
                )
                
                if has_failures:
                    failure_points.append(float(value))
            
            if failure_points:
                boundaries[param_name] = {
                    "failure_points": failure_points,
                    "min_failure": min(failure_points),
                    "max_failure": max(failure_points),
                    "failure_range": max(failure_points) - min(failure_points),
                }
            else:
                boundaries[param_name] = {
                    "failure_points": [],
                    "min_failure": None,
                    "max_failure": None,
                    "failure_range": 0.0,
                }
        
        return boundaries
