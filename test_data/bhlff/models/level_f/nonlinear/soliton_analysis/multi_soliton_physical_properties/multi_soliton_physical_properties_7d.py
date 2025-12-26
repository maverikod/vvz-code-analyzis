"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D BVP properties computation methods for multi-soliton physical properties.

This module provides 7D BVP properties computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class MultiSolitonPhysicalProperties7DMixin:
    """Mixin providing 7D BVP properties computation methods."""
    
    def _compute_fractional_laplacian_contribution(
        self, profile: np.ndarray, x: np.ndarray
    ) -> float:
        """Compute fractional Laplacian contribution."""
        try:
            # Compute fractional Laplacian using FFT
            dx = x[1] - x[0] if len(x) > 1 else 1.0
            profile_fft = np.fft.fft(profile)
            k = np.fft.fftfreq(len(x), dx) * 2 * np.pi
            k_magnitude = np.abs(k)
            k_magnitude[0] = 1e-10  # Avoid division by zero
            
            fractional_spectrum = (k_magnitude ** (2 * self.beta)) * profile_fft
            fractional_laplacian = np.real(np.fft.ifft(fractional_spectrum))
            
            # Compute contribution
            total_energy = np.trapz(profile**2, x)
            frac_energy = np.trapz(profile * fractional_laplacian, x)
            
            if total_energy > 0:
                return abs(frac_energy) / total_energy
            else:
                return 0.0
        
        except Exception as e:
            self.logger.error(
                f"Fractional Laplacian contribution computation failed: {e}"
            )
            return 0.0
    
    def _compute_7d_phase_space_properties(
        self, profile: np.ndarray, x: np.ndarray
    ) -> Dict[str, float]:
        """Compute 7D phase space properties."""
        try:
            # Compute momentum space representation
            profile_fft = np.fft.fft(profile)
            k = np.fft.fftfreq(len(x), x[1] - x[0]) * 2 * np.pi
            
            # Compute phase space volume
            phase_space_volume = np.trapz(np.abs(profile_fft) ** 2, k)
            
            # Compute phase space entropy
            prob_dist = np.abs(profile_fft) ** 2
            prob_dist = prob_dist / np.sum(prob_dist)  # Normalize
            entropy = -np.sum(prob_dist * np.log(prob_dist + 1e-10))
            
            return {
                "phase_space_volume": phase_space_volume,
                "phase_space_entropy": entropy,
                "spectral_width": np.std(k * np.abs(profile_fft)),
            }
        
        except Exception as e:
            self.logger.error(f"7D phase space properties computation failed: {e}")
            return {}
    
    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """Step resonator profile using 7D BVP theory."""
        try:
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)
        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)

