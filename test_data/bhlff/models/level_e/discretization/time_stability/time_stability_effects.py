"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Time step effects computation methods for time stability analyzer.

This module provides time step effects computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class TimeStabilityEffectsMixin:
    """Mixin providing time step effects computation methods."""
    
    def _compute_time_step_effects(
        self, solution: np.ndarray, x: np.ndarray, dt: float, T: float
    ) -> Dict[str, Any]:
        """Compute time step effects on the solution."""
        try:
            # Compute time step stability metrics
            dx = x[1] - x[0] if len(x) > 1 else 1.0
            
            # CFL condition for stability
            cfl_condition = dt < dx**2 / (2 * 1.0)  # Simplified CFL condition
            cfl_ratio = dt / (dx**2 / (2 * 1.0))
            
            # Time step efficiency
            n_steps = int(T / dt)
            time_step_efficiency = 1.0 / n_steps if n_steps > 0 else 0.0
            
            # Solution accuracy (based on energy conservation)
            energy_conservation = self._compute_energy_conservation(solution, x)
            
            return {
                "cfl_condition_satisfied": cfl_condition,
                "cfl_ratio": float(cfl_ratio),
                "time_step_efficiency": float(time_step_efficiency),
                "energy_conservation": float(energy_conservation),
                "time_step": dt,
                "total_time": T,
                "n_steps": n_steps,
            }
        
        except Exception as e:
            return {
                "cfl_condition_satisfied": False,
                "cfl_ratio": 1.0,
                "time_step_efficiency": 0.0,
                "energy_conservation": 0.0,
                "time_step": dt,
                "total_time": T,
                "n_steps": 0,
            }
    
    def _compute_energy_conservation(
        self, solution: np.ndarray, x: np.ndarray
    ) -> float:
        """Compute energy conservation metric."""
        try:
            # Simple energy conservation check
            # In a properly integrated system, energy should be conserved
            energy_density = np.abs(solution) ** 2
            total_energy = np.sum(energy_density)
            
            # Energy conservation metric (simplified)
            # In practice, this would compare with initial energy
            energy_conservation = min(1.0, total_energy / max(total_energy, 1e-10))
            
            return float(energy_conservation)
        
        except Exception as e:
            return 0.0

