"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological charge computation methods for node analyzer.

This module provides topological charge computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List, Tuple


class LevelBNodeAnalyzerTopologyMixin:
    """Mixin providing topological charge computation methods."""
    
    def compute_topological_charge(
        self, field: np.ndarray, center: List[float], contour_points: int = 64
    ) -> Dict[str, Any]:
        """
        Compute topological charge of the defect.
        
        Physical Meaning:
            The topological charge characterizes the degree of "winding"
            of the phase field around the defect and ensures its
            topological stability. Integer values protect the defect
            from continuous deformations.
        """
        # 1. Compute phase field
        phase = np.angle(field)
        
        # 2. Determine integration radius
        radius = self._estimate_integration_radius(field, center)
        
        # 3. Create spherical contour
        contour_points_list = self._create_spherical_contour(
            center, radius, contour_points
        )
        
        # 4. Compute phase gradient
        grad_phase = self._compute_phase_gradient(phase, field.shape)
        
        # 5. Integrate around contour
        charge = self._integrate_phase_around_contour(grad_phase, contour_points_list)
        
        # 6. Normalize to 2π
        normalized_charge = charge / (2 * np.pi)
        
        # 7. Check for integer value
        integer_charge = round(normalized_charge)
        error = abs(normalized_charge - integer_charge)
        
        # 8. Acceptance criteria
        passed = error < 0.01  # Error ≤1%
        
        return {
            "charge": normalized_charge,
            "integer_charge": integer_charge,
            "error": error,
            "passed": passed,
            "contour_points": contour_points_list,
            "integration_radius": radius,
        }
    
    def _estimate_integration_radius(
        self, field: np.ndarray, center: List[float]
    ) -> float:
        """Estimate optimal radius for integration."""
        radial_profile = self._compute_radial_profile(field, center)
        
        max_amplitude = np.max(radial_profile["A"])
        threshold = 0.1 * max_amplitude
        
        below_threshold = radial_profile["A"] < threshold
        if np.any(below_threshold):
            radius = radial_profile["r"][np.where(below_threshold)[0][0]]
        else:
            radius = 0.5 * np.min(field.shape[:3])
        
        return radius
    
    def _create_spherical_contour(
        self, center: List[float], radius: float, n_points: int
    ) -> List[Tuple[float, float, float]]:
        """Create spherical contour for integration."""
        contour = []
        for i in range(n_points):
            angle = 2 * np.pi * i / n_points
            x = center[0] + radius * np.cos(angle)
            y = center[1] + radius * np.sin(angle)
            z = center[2]  # Contour in z = const plane
            contour.append((x, y, z))
        
        return contour
    
    def _compute_phase_gradient(
        self, phase: np.ndarray, field_shape: Tuple[int, ...]
    ) -> np.ndarray:
        """Compute phase gradient."""
        grad_x = np.gradient(phase, axis=0)
        grad_y = np.gradient(phase, axis=1)
        grad_z = np.gradient(phase, axis=2)
        
        return np.stack([grad_x, grad_y, grad_z], axis=-1)
    
    def _integrate_phase_around_contour(
        self, grad_phase: np.ndarray, contour_points: List[Tuple[float, float, float]]
    ) -> float:
        """Integrate phase gradient around contour."""
        charge = 0.0
        
        for i in range(len(contour_points)):
            p1 = np.array(contour_points[i])
            p2 = np.array(contour_points[(i + 1) % len(contour_points)])
            
            mid_point = (p1 + p2) / 2
            grad_mid = self._interpolate_gradient(grad_phase, mid_point)
            
            dl = p2 - p1
            charge += np.dot(grad_mid, dl)
        
        return charge
    
    def _interpolate_gradient(
        self, grad_phase: np.ndarray, point: np.ndarray
    ) -> np.ndarray:
        """
        Interpolate gradient at given point using trilinear interpolation.
        
        Physical Meaning:
            Computes gradient value at arbitrary point using proper 3D
            trilinear interpolation, ensuring accurate topological charge
            computation for B3 test (requirement: |q̄ - q| ≤ 0.01).
        """
        nx, ny, nz = grad_phase.shape[:3]
        x, y, z = point[0], point[1], point[2]
        
        x = max(0.0, min(x, nx - 1.0))
        y = max(0.0, min(y, ny - 1.0))
        z = max(0.0, min(z, nz - 1.0))
        
        x0, y0, z0 = int(np.floor(x)), int(np.floor(y)), int(np.floor(z))
        x1, y1, z1 = min(x0 + 1, nx - 1), min(y0 + 1, ny - 1), min(z0 + 1, nz - 1)
        
        dx = x - x0
        dy = y - y0
        dz = z - z0
        
        w000 = (1 - dx) * (1 - dy) * (1 - dz)
        w001 = (1 - dx) * (1 - dy) * dz
        w010 = (1 - dx) * dy * (1 - dz)
        w011 = (1 - dx) * dy * dz
        w100 = dx * (1 - dy) * (1 - dz)
        w101 = dx * (1 - dy) * dz
        w110 = dx * dy * (1 - dz)
        w111 = dx * dy * dz
        
        grad_interp = np.zeros(3)
        for comp in range(3):
            grad_comp = grad_phase[:, :, :, comp]
            grad_interp[comp] = (
                w000 * grad_comp[x0, y0, z0]
                + w001 * grad_comp[x0, y0, z1]
                + w010 * grad_comp[x0, y1, z0]
                + w011 * grad_comp[x0, y1, z1]
                + w100 * grad_comp[x1, y0, z0]
                + w101 * grad_comp[x1, y0, z1]
                + w110 * grad_comp[x1, y1, z0]
                + w111 * grad_comp[x1, y1, z1]
            )
        
        return grad_interp

