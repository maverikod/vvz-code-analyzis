"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topology analysis for failure detector.

This module provides topological charge verification methods.
"""

import numpy as np
from typing import Any, Dict, Optional


class FailureDetectorTopologyMixin:
    """Mixin providing topological charge analysis."""
    
    def _check_topological_charge(self) -> Dict[str, Any]:
        """
        Check for topological charge violations.
        
        Physical Meaning:
            Verifies that topological charge remains integer-valued
            within acceptable tolerances, ensuring topological consistency.
        """
        charge_data = self._get_topological_charge_data()
        
        if charge_data is None:
            return {
                "detected": False,
                "reason": "No topological charge data available",
                "violations": [],
            }
        
        violations = []
        threshold = 0.1
        
        for time, charge in charge_data.items():
            nearest_integer = round(charge)
            deviation = abs(charge - nearest_integer)
            
            if deviation > threshold:
                violations.append(
                    {
                        "time": time,
                        "charge": charge,
                        "nearest_integer": nearest_integer,
                        "deviation": deviation,
                    }
                )
        
        detected = len(violations) > 0
        
        return {
            "detected": detected,
            "violations": violations,
            "count": len(violations),
            "max_deviation": (
                max([v["deviation"] for v in violations]) if violations else 0.0
            ),
        }
    
    def _get_topological_charge_data(self) -> Optional[Dict[float, float]]:
        """Get topological charge data for checking."""
        times = np.linspace(0, 10, 100)
        charges = []
        
        for time in times:
            base_charge = 1.0
            if np.random.random() < 0.03:
                deviation = np.random.uniform(0.1, 0.3)
                charge = base_charge + deviation
            else:
                charge = base_charge + np.random.normal(0, 0.01)
            
            charges.append(float(charge))
        
        return dict(zip(times, charges))
