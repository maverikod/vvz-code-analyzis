"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for BVP source generators.

This module provides helper methods as a mixin class.
"""

import numpy as np


class BVPSourceGeneratorsHelpersMixin:
    """Mixin providing helper methods."""
    
    def _create_layer_wall(
        self, r: np.ndarray, radius: float, thickness: float, xp=np
    ) -> np.ndarray:
        """Create a layer wall at specified radius with given thickness."""
        # Create smooth wall using sigmoid function
        wall_center = radius
        wall_width = thickness

        # Sigmoid function for smooth wall
        wall_mask = 1.0 / (1.0 + xp.exp(-(r - wall_center) / wall_width))

        # Threshold to get binary wall
        return wall_mask > 0.5
    
    def _regularize_walls(
        self, substrate: np.ndarray, regularization: float
    ) -> np.ndarray:
        """Apply regularization to smooth wall boundaries."""
        # Simple Gaussian smoothing
        from scipy import ndimage

        # Apply 3D Gaussian filter to spatial dimensions only
        smoothed = substrate.copy()
        for t in range(substrate.shape[6]):
            for phi3 in range(substrate.shape[5]):
                for phi2 in range(substrate.shape[4]):
                    for phi1 in range(substrate.shape[3]):
                        smoothed[:, :, :, phi1, phi2, phi3, t] = (
                            ndimage.gaussian_filter(
                                substrate[:, :, :, phi1, phi2, phi3, t],
                                sigma=regularization,
                            )
                        )

        return smoothed
    
    def _step_resonator_source(
        self, r_squared: np.ndarray, width: float, xp=np
    ) -> np.ndarray:
        """
        Step resonator source according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function source instead of exponential decay
            according to 7D BVP theory principles.
        """
        cutoff_radius_squared = (width * 2.0) ** 2  # 2-sigma cutoff
        return xp.where(r_squared < cutoff_radius_squared, 1.0, 0.0)

