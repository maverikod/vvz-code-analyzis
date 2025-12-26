"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Stepwise structure analysis methods for node analyzer.

This module provides stepwise structure analysis methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class LevelBNodeAnalyzerStepwiseMixin:
    """Mixin providing stepwise structure analysis methods."""
    
    def check_stepwise_structure(
        self, field: np.ndarray, center: List[float]
    ) -> Dict[str, Any]:
        """
        Check for stepwise structure instead of simple monotonicity.
        
        Physical Meaning:
            Verifies discrete layered structure with quantized transitions
            instead of simple monotonic decay.
        """
        # 1. Detect stepwise pattern
        stepwise_pattern = self._detect_stepwise_pattern(field, center)
        
        # 2. Check level quantization
        level_quantization = self._check_level_quantization(field, center)
        
        # 3. Verify discrete layers
        discrete_layers = self._verify_discrete_layers(field, center)
        
        # 4. Acceptance criteria for stepwise structure validation
        passed = stepwise_pattern and discrete_layers
        
        return {
            "stepwise_structure": stepwise_pattern,
            "level_quantization": level_quantization,
            "discrete_layers": discrete_layers,
            "passed": passed,
        }
    
    def _detect_stepwise_pattern(self, field: np.ndarray, center: List[float]) -> bool:
        """Detect stepwise pattern in field structure."""
        radial_profile = self._compute_radial_profile(field, center)
        
        gradient = np.gradient(radial_profile["A"], radial_profile["r"])
        second_derivative = np.gradient(gradient, radial_profile["r"])
        
        gradient_threshold = np.std(gradient) * 2
        sharp_transitions = np.abs(gradient) > gradient_threshold
        
        num_transitions = np.sum(sharp_transitions)
        
        return num_transitions > 0
    
    def _check_level_quantization(self, field: np.ndarray, center: List[float]) -> bool:
        """Check for level quantization in stepwise structure."""
        radial_profile = self._compute_radial_profile(field, center)
        
        from scipy.signal import find_peaks
        
        peaks, _ = find_peaks(radial_profile["A"])
        valleys, _ = find_peaks(-radial_profile["A"])
        
        if len(peaks) > 1:
            peak_values = radial_profile["A"][peaks]
            peak_spacing = np.diff(peak_values)
            if len(peak_spacing) > 0:
                mean_spacing = np.mean(peak_spacing)
                std_spacing = np.std(peak_spacing)
                quantized = std_spacing / mean_spacing < 0.2  # 20% tolerance
            else:
                quantized = False
        else:
            quantized = False
        
        return quantized
    
    def _verify_discrete_layers(self, field: np.ndarray, center: List[float]) -> bool:
        """Verify discrete layered structure."""
        radial_profile = self._compute_radial_profile(field, center)
        
        amplitude = radial_profile["A"]
        radius = radial_profile["r"]
        
        gradient = np.gradient(amplitude, radius)
        second_derivative = np.gradient(gradient, radius)
        
        gradient_changes = np.abs(np.diff(gradient))
        threshold = np.std(gradient_changes) * 1.5
        
        significant_changes = np.sum(gradient_changes > threshold)
        
        return significant_changes > 0

