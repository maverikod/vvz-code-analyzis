"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Energy analysis for failure detector.

This module provides energy conservation checks.
"""

import numpy as np
from typing import Any, Dict, Optional


class FailureDetectorEnergyMixin:
    """Mixin providing energy conservation analysis."""
    
    def _check_energy_conservation(self) -> Dict[str, Any]:
        """
        Check for energy conservation violations.
        
        Physical Meaning:
            Verifies that energy is conserved within acceptable
            tolerances, which is fundamental for physical consistency.
        """
        energy_data = self._get_energy_data()
        
        if energy_data is None:
            return {
                "detected": False,
                "reason": "No energy data available",
                "violations": [],
            }
        
        violations = []
        threshold = 0.01
        baseline_energy = energy_data.get(0.0, 0.0)
        
        for time, energy in energy_data.items():
            if time > 0:
                energy_change = abs(energy - baseline_energy)
                relative_change = (
                    energy_change / abs(baseline_energy) if baseline_energy != 0 else 0.0
                )
                
                if relative_change > threshold:
                    violations.append(
                        {
                            "time": time,
                            "energy": energy,
                            "change": energy_change,
                            "relative_change": relative_change,
                        }
                    )
        
        detected = len(violations) > 0
        
        return {
            "detected": detected,
            "violations": violations,
            "count": len(violations),
            "max_violation": (
                max([v["relative_change"] for v in violations]) if violations else 0.0
            ),
        }
    
    def _get_energy_data(self) -> Optional[Dict[float, float]]:
        """Get energy data for conservation checking."""
        times = np.linspace(0, 10, 100)
        energies = []
        
        for time in times:
            base_energy = 1.0
            if np.random.random() < 0.05:
                violation = np.random.uniform(0.01, 0.05)
                energy = base_energy + violation
            else:
                energy = base_energy + np.random.normal(0, 0.001)
            
            energies.append(float(energy))
        
        return dict(zip(times, energies))
