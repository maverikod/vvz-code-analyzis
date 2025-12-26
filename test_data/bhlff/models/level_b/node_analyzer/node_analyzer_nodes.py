"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Node detection methods for node analyzer.

This module provides node detection methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class LevelBNodeAnalyzerNodesMixin:
    """Mixin providing node detection methods."""
    
    def check_spherical_nodes(
        self, field: np.ndarray, center: List[float], max_sign_changes: int = 1
    ) -> Dict[str, Any]:
        """
        Check for absence of spherical standing nodes.
        
        Physical Meaning:
            In pure fractional regime (λ=0), the operator symbol D(k) = μk^(2β)
            has no poles, preventing formation of spherical standing waves
            and ensuring monotonic field decay.
        """
        # 1. Compute radial profile
        radial_profile = self._compute_radial_profile(field, center)
        r = radial_profile["r"]
        A = radial_profile["A"]
        
        # 2. Compute radial derivative
        dA_dr = np.gradient(A, r)
        
        # 3. Count sign changes in derivative
        sign_changes = self._count_sign_changes(dA_dr)
        
        # 4. Find amplitude zeros
        zeros = self._find_amplitude_zeros(A, r)
        
        # 5. Check for periodicity in zeros
        periodic_zeros = self._check_periodicity(zeros)
        
        # 6. Analyze monotonicity
        is_monotonic = self._check_monotonicity(A, r)
        
        # 7. Acceptance criteria
        passed = (
            sign_changes <= max_sign_changes
            and not periodic_zeros
            and is_monotonic
        )
        
        return {
            "sign_changes": sign_changes,
            "zeros": zeros,
            "periodic_zeros": periodic_zeros,
            "is_monotonic": is_monotonic,
            "passed": passed,
            "radial_derivative": dA_dr,
            "radial_profile": radial_profile,
        }
    
    def _count_sign_changes(self, derivative: np.ndarray) -> int:
        """Count sign changes in derivative."""
        signs = np.sign(derivative)
        sign_changes = np.sum(np.diff(signs) != 0)
        return sign_changes
    
    def _find_amplitude_zeros(
        self, amplitude: np.ndarray, radius: np.ndarray
    ) -> np.ndarray:
        """Find zeros in amplitude."""
        # Exclude core region
        core_region = radius < 0.1 * radius.max()
        tail_amplitude = amplitude[~core_region]
        tail_radius = radius[~core_region]
        
        # Find zero crossings
        zero_crossings = []
        for i in range(len(tail_amplitude) - 1):
            if tail_amplitude[i] * tail_amplitude[i + 1] < 0:
                r_zero = np.interp(
                    0,
                    [tail_amplitude[i], tail_amplitude[i + 1]],
                    [tail_radius[i], tail_radius[i + 1]],
                )
                zero_crossings.append(r_zero)
        
        return np.array(zero_crossings)
    
    def _check_periodicity(self, zeros: np.ndarray, tolerance: float = 0.1) -> bool:
        """Check for periodicity in zeros."""
        if len(zeros) < 3:
            return False
        
        intervals = np.diff(zeros)
        if len(intervals) < 2:
            return False
        
        mean_interval = np.mean(intervals)
        relative_std = np.std(intervals) / mean_interval
        
        return relative_std < tolerance
    
    def _check_monotonicity(self, amplitude: np.ndarray, radius: np.ndarray) -> bool:
        """Check for monotonic decay."""
        smoothed = np.convolve(amplitude, np.ones(5) / 5, mode="valid")
        if len(smoothed) < 2:
            return True
        
        trend = np.polyfit(radius[: len(smoothed)], smoothed, 1)[0]
        return trend < 0

