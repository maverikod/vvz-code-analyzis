"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary detection module for zone analysis.

This module implements boundary detection operations for zone analysis,
including level set analysis, phase field methods, and topological analysis.

Physical Meaning:
    Identifies boundaries between different zones using complete 7D analysis
    according to the 7D theory.

Mathematical Foundation:
    Implements full boundary detection:
    - Level set analysis
    - Phase field method
    - Topological analysis
    - Energy landscape analysis
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class BoundaryDetection:
    """
    Boundary detection for zone analysis.

    Physical Meaning:
        Identifies boundaries between different zones using complete 7D analysis
        according to the 7D theory.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize boundary detector."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def identify_zone_boundaries(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Identify zone boundaries using full 7D analysis.

        Physical Meaning:
            Identifies boundaries between different zones (core, transition, tail)
            using complete 7D analysis according to the 7D theory.
        """
        amplitude = np.abs(envelope)

        # Level set analysis for boundary detection
        level_sets = self._compute_level_sets(amplitude)

        # Phase field method for boundary evolution
        phase_field_boundaries = self._compute_phase_field_boundaries(amplitude)

        # Topological analysis of boundaries
        topological_boundaries = self._analyze_boundary_topology(amplitude)

        # Energy landscape analysis
        energy_landscape = self._compute_energy_landscape(amplitude)

        return {
            "level_set_boundaries": level_sets,
            "phase_field_boundaries": phase_field_boundaries,
            "topological_boundaries": topological_boundaries,
            "energy_landscape": energy_landscape,
        }

    def _compute_level_sets(self, amplitude: np.ndarray) -> Dict[str, Any]:
        """Compute level sets for boundary detection."""
        # Define level set thresholds
        max_amp = np.max(amplitude)
        min_amp = np.min(amplitude)

        # Create level sets at different thresholds
        level_sets = {}
        thresholds = np.linspace(min_amp, max_amp, 10)

        for i, threshold in enumerate(thresholds):
            # Create level set
            level_set = amplitude >= threshold

            # Compute level set properties
            level_set_properties = {
                "threshold": float(threshold),
                "volume_fraction": float(np.sum(level_set) / level_set.size),
                "boundary_length": self._compute_boundary_length(level_set),
                "connectivity": self._compute_connectivity(level_set),
            }

            level_sets[f"level_{i}"] = level_set_properties

        return level_sets

    def _compute_phase_field_boundaries(self, amplitude: np.ndarray) -> Dict[str, Any]:
        """Compute boundaries using phase field method."""
        # Compute phase field order parameter
        max_amp = np.max(amplitude)
        phase_field = amplitude / max_amp

        # Compute phase field gradients
        gradients = self._compute_phase_field_gradients(phase_field)

        # Identify boundary regions (high gradient regions)
        gradient_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))
        boundary_threshold = np.percentile(gradient_magnitude, 90)
        boundary_mask = gradient_magnitude > boundary_threshold

        # Compute boundary properties
        boundary_properties = {
            "boundary_mask": boundary_mask,
            "gradient_magnitude": gradient_magnitude,
            "boundary_threshold": float(boundary_threshold),
            "boundary_density": float(np.sum(boundary_mask) / boundary_mask.size),
            "gradients": gradients,
        }

        return boundary_properties

    def _analyze_boundary_topology(self, amplitude: np.ndarray) -> Dict[str, Any]:
        """Analyze topology of boundaries."""
        # Compute field gradients
        gradients = self._compute_field_gradients(amplitude)

        # Compute curvature of level sets
        curvature = self._compute_curvature(amplitude, gradients)

        # Identify critical points
        critical_points = self._identify_critical_points(gradients)

        # Compute topological invariants
        topological_invariants = self._compute_topological_invariants(
            amplitude, gradients
        )

        return {
            "curvature": curvature,
            "critical_points": critical_points,
            "topological_invariants": topological_invariants,
            "gradients": gradients,
        }

    def _compute_energy_landscape(self, amplitude: np.ndarray) -> Dict[str, Any]:
        """Compute energy landscape for boundary analysis."""
        # Compute local energy density
        energy_density = self._compute_energy_density(amplitude)

        # Compute energy gradients
        energy_gradients = self._compute_energy_gradients(energy_density)

        # Identify energy barriers
        energy_barriers = self._identify_energy_barriers(
            energy_density, energy_gradients
        )

        # Compute transition regions
        transition_regions = self._identify_transition_regions(energy_density)

        return {
            "energy_density": energy_density,
            "energy_gradients": energy_gradients,
            "energy_barriers": energy_barriers,
            "transition_regions": transition_regions,
        }

    def _compute_boundary_length(self, level_set: np.ndarray) -> float:
        """
        Compute boundary length of level set using proper geometric measure.

        Physical Meaning:
            Computes the length (2D) or surface area (3D+) of the boundary
            between different regions in the level set, using proper
            geometric measure appropriate for the dimensionality.

        Mathematical Foundation:
            For discrete grid, boundary length is computed as the sum of
            edge lengths/face areas where the level set value changes.
            For N-dimensional level set, boundary is (N-1)-dimensional
            manifold with proper measure.

        Args:
            level_set (np.ndarray): Binary or thresholded level set array

        Returns:
            float: Boundary length/surface area
        """
        boundary_length = 0.0

        if level_set.ndim >= 2:
            # For N-dimensional case, compute boundary as sum of (N-1)-dimensional faces
            # where level set changes value
            level_set_int = level_set.astype(int)

            for axis in range(level_set.ndim):
                # Compute differences along this axis
                diff = np.diff(level_set_int, axis=axis)
                # Boundary exists where diff != 0
                boundary_edges = np.abs(diff) > 0

                # Count boundary elements, weighted by proper geometric measure
                # For grid spacing = 1, this gives correct boundary measure
                boundary_length += np.sum(boundary_edges.astype(float))
        else:
            # 1D case: boundary is just number of transitions
            level_set_int = level_set.astype(int)
            diff = np.diff(level_set_int)
            boundary_length = float(np.sum(np.abs(diff) > 0))

        return float(boundary_length)

    def _compute_connectivity(self, level_set: np.ndarray) -> Dict[str, Any]:
        """Compute connectivity properties of level set."""
        # Count connected components
        try:
            from scipy import ndimage

            labeled, num_components = ndimage.label(level_set)

            # Compute component sizes
            component_sizes = []
            for i in range(1, num_components + 1):
                size = np.sum(labeled == i)
                component_sizes.append(size)

            return {
                "num_components": num_components,
                "component_sizes": component_sizes,
                "largest_component": max(component_sizes) if component_sizes else 0,
                "connectivity_ratio": (
                    max(component_sizes) / np.sum(level_set)
                    if np.sum(level_set) > 0
                    else 0
                ),
            }
        except ImportError:
            # Fallback if scipy not available
            return {
                "num_components": 1,
                "component_sizes": [np.sum(level_set)],
                "largest_component": np.sum(level_set),
                "connectivity_ratio": 1.0,
            }

    def _compute_phase_field_gradients(
        self, phase_field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Compute gradients of phase field."""
        gradients = {}

        for dim in range(phase_field.ndim):
            gradient = np.gradient(phase_field, axis=dim)
            gradients[f"dim_{dim}"] = gradient

        return gradients

    def _compute_field_gradients(self, field: np.ndarray) -> Dict[str, np.ndarray]:
        """Compute gradients of field."""
        gradients = {}

        for dim in range(field.ndim):
            gradient = np.gradient(field, axis=dim)
            gradients[f"dim_{dim}"] = gradient

        return gradients

    def _compute_curvature(
        self, field: np.ndarray, gradients: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """Compute curvature of level sets."""
        if field.ndim >= 2:
            # Compute second derivatives
            second_derivatives = {}
            for dim in range(field.ndim):
                second_derivatives[f"dim_{dim}"] = np.gradient(
                    gradients[f"dim_{dim}"], axis=dim
                )

            # Compute mean curvature for N-dimensional field
            # Mean curvature: κ = div(n̂) where n̂ = ∇f / |∇f| is unit normal
            if field.ndim == 2:
                # 2D case: κ = (f_xx * f_y² - 2*f_xy*f_x*f_y + f_yy*f_x²) / (f_x² + f_y²)^(3/2)
                f_x = gradients["dim_0"]
                f_y = gradients["dim_1"]
                f_xx = second_derivatives["dim_0"]
                f_yy = second_derivatives["dim_1"]

                # Approximate f_xy
                f_xy = np.gradient(f_x, axis=1)

                denominator = (f_x**2 + f_y**2) ** (3 / 2)
                denominator = np.where(denominator < 1e-10, 1e-10, denominator)

                curvature = (
                    f_xx * f_y**2 - 2 * f_xy * f_x * f_y + f_yy * f_x**2
                ) / denominator
            else:
                # Higher dimensions: proper mean curvature formula
                # κ = (1/(n-1)) * div(n̂), where n̂ = ∇f / |∇f|

                # Compute gradient magnitude
                grad_mag_sq = sum(grad**2 for grad in gradients.values())
                grad_mag = np.sqrt(grad_mag_sq)
                grad_mag_safe = np.where(grad_mag < 1e-10, 1e-10, grad_mag)

                # Unit normal components: n_i = f_i / |∇f|
                unit_normals = {
                    dim: grad / grad_mag_safe for dim, grad in gradients.items()
                }

                # Compute divergence of unit normal: div(n̂) = Σ_i ∂n_i/∂x_i
                div_normal = np.zeros_like(field)
                for dim_idx, (dim, n_i) in enumerate(unit_normals.items()):
                    div_n_i = np.gradient(n_i, axis=dim_idx)
                    div_normal += div_n_i

                # Mean curvature: κ = div(n̂) / (n-1) for n-dimensional hypersurface
                # For level set in nD space, mean curvature is div(n̂) / (n-1)
                n_dims = field.ndim
                curvature = div_normal / max(1, n_dims - 1)
        else:
            # 1D case
            curvature = np.gradient(gradients["dim_0"], axis=0)

        return curvature

    def _identify_critical_points(
        self, gradients: Dict[str, np.ndarray]
    ) -> List[Dict[str, Any]]:
        """Identify critical points where gradients are zero."""
        critical_points = []

        # Find points where all gradients are close to zero
        gradient_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))
        critical_mask = gradient_magnitude < np.percentile(gradient_magnitude, 5)

        # Find critical point coordinates
        critical_coords = np.where(critical_mask)

        for i in range(len(critical_coords[0])):
            coords = tuple(
                critical_coords[dim][i] for dim in range(len(critical_coords))
            )
            critical_points.append(
                {
                    "coordinates": coords,
                    "gradient_magnitude": float(gradient_magnitude[coords]),
                    "type": "critical_point",
                }
            )

        return critical_points

    def _compute_topological_invariants(
        self, field: np.ndarray, gradients: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """Compute topological invariants of the field."""
        # Compute basic topological measures
        gradient_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

        # Compute topological measures
        max_gradient = np.max(gradient_magnitude)
        mean_gradient = np.mean(gradient_magnitude)
        gradient_variance = np.var(gradient_magnitude)

        # Compute field topology
        field_max = np.max(field)
        field_min = np.min(field)
        field_range = field_max - field_min

        return {
            "max_gradient": float(max_gradient),
            "mean_gradient": float(mean_gradient),
            "gradient_variance": float(gradient_variance),
            "field_range": float(field_range),
            "topological_complexity": (
                float(gradient_variance / mean_gradient) if mean_gradient > 0 else 0.0
            ),
        }

    def _compute_energy_density(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute full 7D BVP energy density functional.

        Physical Meaning:
            Computes the complete energy density according to 7D BVP theory,
            including gradient energy contributions from all 7 dimensions.
            This is required for accurate zone separation (B4 test).

        Mathematical Foundation:
            Energy density in 7D BVP theory:
            E = f_φ²|∇_x a|² + f_φ²|∇_φ a|² + β₄(Δa)² + γ₆|∇a|⁶ + ...
            where a is the field amplitude, ∇_x are spatial gradients,
            ∇_φ are phase gradients, and Δ is the Laplacian.

            For amplitude-only case, we use:
            E ≈ μ|∇amplitude|² + λ|amplitude|² + β₄(Δamplitude)²
            where μ and λ are BVP parameters.

        Args:
            amplitude (np.ndarray): Field amplitude (real-valued)

        Returns:
            np.ndarray: Energy density at each point
        """
        # BVP energy density parameters (default values if not specified)
        # In full implementation, these should come from BVP model parameters
        mu = 1.0  # Diffusion coefficient
        lambda_param = 0.1  # Damping parameter
        beta4 = 0.01  # Fourth-order coefficient
        f_phi = 1.0  # Phase field constant

        # Compute gradients along all dimensions
        gradients = self._compute_field_gradients(amplitude)

        # Compute gradient magnitude squared
        gradient_sq = sum(np.abs(grad) ** 2 for grad in gradients.values())

        # Compute Laplacian (sum of second derivatives)
        laplacian = np.zeros_like(amplitude)
        for dim, grad in gradients.items():
            dim_idx = int(dim.split("_")[1])
            second_deriv = np.gradient(grad, axis=dim_idx)
            laplacian += second_deriv

        # Compute Laplacian squared
        laplacian_sq = np.abs(laplacian) ** 2

        # Full 7D BVP energy density
        # E = μ|∇a|² + λ|a|² + β₄(Δa)²
        energy_density = (
            mu * gradient_sq  # Gradient energy: μ|∇a|²
            + lambda_param * amplitude**2  # Potential energy: λ|a|²
            + beta4 * laplacian_sq  # Laplacian energy: β₄(Δa)²
        )

        return energy_density

    def _compute_energy_gradients(
        self, energy_density: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Compute gradients of energy density."""
        return self._compute_field_gradients(energy_density)

    def _identify_energy_barriers(
        self, energy_density: np.ndarray, energy_gradients: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """Identify energy barriers in the landscape."""
        # Find local maxima in energy density
        gradient_magnitude = np.sqrt(sum(grad**2 for grad in energy_gradients.values()))

        # Energy barriers are regions with high energy and low gradient magnitude
        energy_threshold = np.percentile(energy_density, 80)
        gradient_threshold = np.percentile(gradient_magnitude, 20)

        barrier_mask = (energy_density > energy_threshold) & (
            gradient_magnitude < gradient_threshold
        )

        return {
            "barrier_mask": barrier_mask,
            "energy_threshold": float(energy_threshold),
            "gradient_threshold": float(gradient_threshold),
            "barrier_density": float(np.sum(barrier_mask) / barrier_mask.size),
        }

    def _identify_transition_regions(
        self, energy_density: np.ndarray
    ) -> Dict[str, Any]:
        """Identify transition regions in energy landscape."""
        # Transition regions are regions with intermediate energy
        energy_min = np.min(energy_density)
        energy_max = np.max(energy_density)
        energy_range = energy_max - energy_min

        # Define transition region as middle 40% of energy range
        lower_threshold = energy_min + 0.3 * energy_range
        upper_threshold = energy_min + 0.7 * energy_range

        transition_mask = (energy_density >= lower_threshold) & (
            energy_density <= upper_threshold
        )

        return {
            "transition_mask": transition_mask,
            "lower_threshold": float(lower_threshold),
            "upper_threshold": float(upper_threshold),
            "transition_density": float(np.sum(transition_mask) / transition_mask.size),
        }
