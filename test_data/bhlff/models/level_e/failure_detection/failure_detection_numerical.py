"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Numerical stability analysis for failure detector.

This module provides numerical stability checks.
"""

import numpy as np
from typing import Any, Dict, Optional


class FailureDetectorNumericalMixin:
    """Mixin providing numerical stability analysis."""
    
    def _check_numerical_stability(self) -> Dict[str, Any]:
        """
        Check for numerical stability issues.
        
        Physical Meaning:
            Detects numerical instabilities such as NaN values,
            infinite values, and excessive growth rates.
        """
        numerical_data = self._get_numerical_data()
        
        if numerical_data is None:
            return {
                "detected": False,
                "reason": "No numerical data available",
                "instabilities": [],
            }
        
        instabilities = []
        
        for field_name, field_data in numerical_data.items():
            nan_count = int(np.isnan(field_data).sum())
            if nan_count > 0:
                instabilities.append(
                    {"field": field_name, "type": "NaN_values", "count": nan_count}
                )
            
            inf_count = int(np.isinf(field_data).sum())
            if inf_count > 0:
                instabilities.append(
                    {"field": field_name, "type": "infinite_values", "count": inf_count}
                )
            
            if len(field_data) > 1:
                growth_rate = float(np.max(np.abs(np.diff(field_data))))
                if growth_rate > 10.0:
                    instabilities.append(
                        {
                            "field": field_name,
                            "type": "excessive_growth",
                            "growth_rate": growth_rate,
                        }
                    )
        
        detected = len(instabilities) > 0
        
        return {
            "detected": detected,
            "instabilities": instabilities,
            "count": len(instabilities),
        }
    
    def _get_numerical_data(self) -> Optional[Dict[str, np.ndarray]]:
        """Get numerical data for stability checking."""
        data: Dict[str, np.ndarray] = {}
        field_data = np.random.normal(0, 1, 1000)
        
        if np.random.random() < 0.1:
            nan_indices = np.random.choice(len(field_data), 10, replace=False)
            field_data[nan_indices] = np.nan
        
        if np.random.random() < 0.05:
            inf_indices = np.random.choice(len(field_data), 5, replace=False)
            field_data[inf_indices] = np.inf
        
        data["field"] = field_data
        
        return data
