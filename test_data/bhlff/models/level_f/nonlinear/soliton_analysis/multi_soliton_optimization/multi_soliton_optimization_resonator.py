"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonator methods for multi-soliton optimization.

This module provides step resonator methods as a mixin class.
"""

import numpy as np


class MultiSolitonOptimizationResonatorMixin:
    """Mixin providing step resonator methods."""
    
    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """
        Step resonator profile using 7D BVP theory.
        
        Physical Meaning:
            Implements step resonator profile instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at soliton width.
            
        Mathematical Foundation:
            Step resonator profile:
            f(x) = 1 if |x - pos| < width, 0 if |x - pos| ≥ width
            where width is the soliton width parameter.
            
        Args:
            x (np.ndarray): Spatial coordinate array.
            position (float): Soliton position.
            width (float): Soliton width parameter.
            
        Returns:
            np.ndarray: Step resonator profile.
        """
        try:
            # Step resonator: sharp cutoff at soliton width
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)
        
        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)
    
    def _step_resonator_boundary_condition(
        self, field_value: float, amplitude: float
    ) -> float:
        """
        Step resonator boundary condition using 7D BVP theory.
        
        Physical Meaning:
            Implements step resonator boundary condition instead of
            exponential decay, following 7D BVP theory principles.
            
        Args:
            field_value (float): Field value at boundary.
            amplitude (float): Soliton amplitude.
            
        Returns:
            float: Boundary condition value.
        """
        try:
            # Step resonator: sharp boundary condition
            if abs(field_value) < 0.1 * amplitude:
                return 0.0
            else:
                return field_value
        
        except Exception as e:
            self.logger.error(
                f"Step resonator boundary condition computation failed: {e}"
            )
            return field_value

