"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Defect generation methods for BVP source generators.

This module provides defect generation methods as a mixin class.
"""

import numpy as np


class BVPSourceGeneratorsDefectsMixin:
    """Mixin providing defect generation methods."""
    
    def _add_line_defects(
        self,
        substrate: np.ndarray,
        density: float,
        core_radius: float,
        wall_thickness: float,
    ) -> np.ndarray:
        """Add line defects (strings) to substrate."""
        # Simple implementation: add vertical line defects
        num_defects = int(density * self.domain.N**2)

        for _ in range(num_defects):
            # Random line position
            i = np.random.randint(0, self.domain.N)
            j = np.random.randint(0, self.domain.N)

            # Create line defect (low transparency)
            substrate[i, j, :, :, :, :, :] *= 0.1

        return substrate
    
    def _add_surface_defects(
        self,
        substrate: np.ndarray,
        density: float,
        core_radius: float,
        wall_thickness: float,
    ) -> np.ndarray:
        """Add surface defects (domain walls) to substrate."""
        # Simple implementation: add planar defects
        num_defects = int(density * self.domain.N)

        for _ in range(num_defects):
            # Random plane position
            i = np.random.randint(0, self.domain.N)

            # Create surface defect
            substrate[i, :, :, :, :, :, :] *= 0.2

        return substrate
    
    def _add_junction_defects(
        self,
        substrate: np.ndarray,
        density: float,
        core_radius: float,
        wall_thickness: float,
    ) -> np.ndarray:
        """Add junction defects to substrate."""
        # Simple implementation: add point-like junction defects
        num_defects = int(density * self.domain.N**3)

        for _ in range(num_defects):
            # Random junction position
            i = np.random.randint(0, self.domain.N)
            j = np.random.randint(0, self.domain.N)
            k = np.random.randint(0, self.domain.N)

            # Create junction defect (very low transparency)
            substrate[i, j, k, :, :, :, :] *= 0.05

        return substrate
    
    def _add_dislocation_defects(
        self,
        substrate: np.ndarray,
        density: float,
        core_radius: float,
        wall_thickness: float,
    ) -> np.ndarray:
        """Add dislocation defects in phase space to substrate."""
        # Simple implementation: add phase-space dislocations
        num_defects = int(density * self.domain.N_phi**3)

        for _ in range(num_defects):
            # Random dislocation position in phase space
            phi1 = np.random.randint(0, self.domain.N_phi)
            phi2 = np.random.randint(0, self.domain.N_phi)
            phi3 = np.random.randint(0, self.domain.N_phi)

            # Create dislocation defect
            substrate[:, :, :, phi1, phi2, phi3, :] *= 0.15

        return substrate

