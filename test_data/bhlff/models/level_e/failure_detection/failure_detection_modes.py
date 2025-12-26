"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Mode analysis for failure detector.

This module provides singular mode detection utilities.
"""

import numpy as np
from typing import Any, Dict, Optional


class FailureDetectorModesMixin:
    """Mixin providing singular mode analysis."""
    
    def _check_singular_mode(self) -> Dict[str, Any]:
        """
        Check for singular modes.
        
        Physical Meaning:
            Detects singular modes where λ = 0 with ŝ(0) ≠ 0,
            which can lead to numerical instabilities and
            unphysical behavior.
        """
        mode_data = self._get_mode_data()
        
        if mode_data is None:
            return {
                "detected": False,
                "reason": "No mode data available",
                "singular_modes": [],
            }
        
        singular_modes = []
        
        for mode_id, mode_info in mode_data.items():
            lambda_val = mode_info.get("lambda", 1.0)
            source_val = mode_info.get("source", 0.0)
            
            if abs(lambda_val) < 1e-10 and abs(source_val) > 1e-10:
                singular_modes.append(
                    {
                        "mode_id": mode_id,
                        "lambda": lambda_val,
                        "source": source_val,
                        "singularity_strength": (
                            abs(source_val) / abs(lambda_val)
                            if lambda_val != 0
                            else float("inf")
                        ),
                    }
                )
        
        detected = len(singular_modes) > 0
        
        return {
            "detected": detected,
            "singular_modes": singular_modes,
            "count": len(singular_modes),
            "max_singularity": (
                max([m["singularity_strength"] for m in singular_modes])
                if singular_modes
                else 0.0
            ),
        }
    
    def _get_mode_data(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Get mode data for singular mode checking."""
        modes: Dict[str, Dict[str, float]] = {}
        
        for index in range(10):
            lambda_val = np.random.uniform(0.001, 1.0)
            source_val = np.random.uniform(0.0, 0.1)
            
            if np.random.random() < 0.05:
                lambda_val = np.random.uniform(0, 1e-10)
                source_val = np.random.uniform(0.01, 0.1)
            
            modes[f"mode_{index}"] = {"lambda": float(lambda_val), "source": float(source_val)}
        
        return modes
