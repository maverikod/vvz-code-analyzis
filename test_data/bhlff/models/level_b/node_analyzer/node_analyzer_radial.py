"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radial profile computation methods for node analyzer.

This module provides radial profile computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class LevelBNodeAnalyzerRadialMixin:
    """Mixin providing radial profile computation methods."""
    
    def _compute_radial_profile(
        self, field: np.ndarray, center: List[float]
    ) -> Dict[str, np.ndarray]:
        """Compute radial profile of the field."""
        # Get field shape (assuming 3D spatial dimensions)
        if len(field.shape) == 7:
            shape = field.shape[:3]  # Take first 3 spatial dimensions
        else:
            shape = field.shape[:3]  # Take first 3 dimensions
        
        # Create coordinate grids
        x = np.arange(shape[0])
        y = np.arange(shape[1])
        z = np.arange(shape[2])
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        # Compute distances from center
        distances = np.sqrt(
            (X - center[0]) ** 2 + (Y - center[1]) ** 2 + (Z - center[2]) ** 2
        )
        
        # Get field amplitude
        if len(field.shape) == 7:
            # For 7D field, take slice at center of other dimensions
            center_phi = field.shape[3] // 2
            center_t = field.shape[6] // 2
            amplitude = np.abs(
                field[:, :, :, center_phi, center_phi, center_phi, center_t]
            )
        else:
            amplitude = np.abs(field)
        
        # Create radial bins
        r_max = np.max(distances)
        r_bins = np.linspace(0, r_max, min(100, int(r_max)))
        r_centers = (r_bins[:-1] + r_bins[1:]) / 2
        
        # Bin the data
        A_radial = []
        for i in range(len(r_bins) - 1):
            mask = (distances >= r_bins[i]) & (distances < r_bins[i + 1])
            if np.any(mask):
                A_radial.append(np.mean(amplitude[mask]))
            else:
                A_radial.append(0.0)
        
        return {"r": r_centers, "A": np.array(A_radial)}

