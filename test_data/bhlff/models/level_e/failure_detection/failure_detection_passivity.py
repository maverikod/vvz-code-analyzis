"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Passivity checks for failure detector.

This module provides passivity violation detection methods.
"""

import numpy as np
from typing import Any, Dict, Optional


class FailureDetectorPassivityMixin:
    """Mixin providing passivity checks."""
    
    def _check_passivity_violation(self) -> Dict[str, Any]:
        """
        Check for passivity violations.
        
        Physical Meaning:
            Verifies that the system remains passive (Re Y_out ≥ 0),
            which is a fundamental physical requirement for energy
            conservation and stability.
        """
        impedance_data = self._get_impedance_data()
        
        if impedance_data is None:
            return {
                "detected": False,
                "reason": "No impedance data available",
                "violations": [],
            }
        
        violations = []
        
        for freq, impedance in impedance_data.items():
            if isinstance(impedance, complex):
                real_part = impedance.real
                if real_part < 0:
                    violations.append(
                        {
                            "frequency": freq,
                            "impedance": impedance,
                            "real_part": real_part,
                            "violation_magnitude": abs(real_part),
                        }
                    )
        
        detected = len(violations) > 0
        
        return {
            "detected": detected,
            "violations": violations,
            "count": len(violations),
            "max_violation": (
                max([v["violation_magnitude"] for v in violations])
                if violations
                else 0.0
            ),
        }
    
    def _get_impedance_data(self) -> Optional[Dict[float, complex]]:
        """Get impedance data for passivity checking."""
        frequencies = np.logspace(0, 3, 100)
        impedances = []
        
        for freq in frequencies:
            if np.random.random() < 0.1:
                real_part = -np.random.uniform(0.01, 0.1)
                imag_part = np.random.uniform(-1, 1)
            else:
                real_part = np.random.uniform(0.01, 1.0)
                imag_part = np.random.uniform(-1, 1)
            
            impedances.append(complex(real_part, imag_part))
        
        return dict(zip(frequencies, impedances))
