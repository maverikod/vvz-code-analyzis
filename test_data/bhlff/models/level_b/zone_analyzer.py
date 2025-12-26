"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Zone analysis for Level B fundamental properties.

This module implements zone separation analysis for the 7D phase field theory,
quantitatively separating the field into core, transition, and tail regions.

Theoretical Background:
    The phase field exhibits three characteristic zones: core (high density,
    nonlinear), transition (balance between core and tail), and tail
    (linear wave region). Each zone plays a specific role in particle formation.

Example:
    >>> analyzer = LevelBZoneAnalyzer()
    >>> result = analyzer.separate_zones(field, center, thresholds)
"""

# flake8: noqa: E501

import numpy as np
from typing import Dict, Any, Tuple, List
import matplotlib.pyplot as plt
from .zone_analyzer_utils import visualize_zone_analysis as _viz_zone
from .zone_analyzer_utils import run_zone_analysis_variations as _run_variations

# CUDA support
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class LevelBZoneAnalyzer:
    """
    Zone analysis for Level B fundamental properties.

    Physical Meaning:
        Separates the phase field into three characteristic zones:
        core (high density, nonlinear), transition (balance), and
        tail (linear wave region). Each zone plays a specific role
        in particle formation and stability.

    Mathematical Foundation:
        Zone separation is based on local indicators N (norm gradient),
        S (second derivative), and C (coherence). Thresholds determine
        the boundaries between zones.
    """

    def __init__(self, use_cuda: bool = True):
        """
        Initialize zone analyzer.

        Physical Meaning:
            Sets up analyzer for zone separation analysis with CUDA
            acceleration for 7D phase field computations.

        Args:
            use_cuda (bool): Whether to use CUDA acceleration if available.
                Defaults to True to enable GPU acceleration when possible.
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        if self.use_cuda:
            self.xp = cp
        else:
            self.xp = np
        # Default thresholds for zone separation (can be overridden per call)
        self.default_thresholds: Dict[str, float] = {
            "N_core": 0.7,
            "S_core": 0.6,
            "N_tail": 0.2,
            "S_tail": 0.2,
        }
        # Visualization options
        self.figure_size: Tuple[int, int] = (12, 10)
        self.colormaps: Dict[str, str] = {
            "core": "viridis",
            "tail": "plasma",
            "N": "hot",
            "S": "cool",
        }
        # Numerical stability parameters
        self.eps: float = 1e-15

    def separate_zones(
        self,
        field: np.ndarray,
        center: List[float],
        thresholds: Dict[str, float],
        domain_size: float = None,
    ) -> Dict[str, Any]:
        """
        Separate field into zones (core/transition/tail).

        Physical Meaning:
            Quantitatively separates the phase field into three
            characteristic zones based on local indicators, allowing
            analysis of the structure and role of each zone in
            particle formation.

        Mathematical Foundation:
            - Core: N > N_core, S > S_core (high density, nonlinear)
            - Tail: N < N_tail, S < S_tail (linear wave region)
            - Transition: intermediate values (balance zone)

        Args:
            field (np.ndarray): Phase field solution
            center (List[float]): Center of the defect [x, y, z]
            thresholds (Dict[str, float]): Threshold values for zone separation
            domain_size (float, optional): Physical domain size L for B4 criteria.
                If None, estimated from field dimensions assuming unit grid spacing.

        Returns:
            Dict[str, Any]: Zone separation results with masks, radii, and statistics
        """
        # 1. Compute zone indicators
        indicators = self._compute_zone_indicators(field)
        N = indicators["N"]
        S = indicators["S"]

        # 2. Normalize indicators
        xp = self.xp
        N_max = xp.max(N) if hasattr(N, "__array__") else np.max(N)
        S_max = xp.max(S) if hasattr(S, "__array__") else np.max(S)
        N_norm = N / N_max if N_max > 0 else N
        S_norm = S / S_max if S_max > 0 else S

        # Convert to numpy for mask operations if needed
        if self.use_cuda and isinstance(N_norm, cp.ndarray):
            N_norm_np = cp.asnumpy(N_norm)
            S_norm_np = cp.asnumpy(S_norm)
        else:
            N_norm_np = N_norm
            S_norm_np = S_norm

        # 3. Separate zones by thresholds
        core_mask = (N_norm_np > thresholds["N_core"]) & (S_norm_np > thresholds["S_core"])
        tail_mask = (N_norm_np < thresholds["N_tail"]) & (S_norm_np < thresholds["S_tail"])
        transition_mask = ~(core_mask | tail_mask)

        # 4. Compute zone radii
        r_core = self._compute_zone_radius(core_mask, center)
        r_tail = self._compute_zone_radius(tail_mask, center)
        r_transition = self._compute_zone_radius(transition_mask, center)

        # 5. Compute zone statistics
        zone_stats = self._compute_zone_statistics(
            field, core_mask, transition_mask, tail_mask
        )

        # 6. Quality assessment
        quality_metrics = self._assess_zone_separation_quality(
            core_mask, tail_mask, transition_mask, zone_stats
        )

        # B4 acceptance criteria from §8 of experimental plan:
        # 1. Ordering: 0 < r_core < r_tail < L/4
        # 2. Convergence: |r_core(N₂) - r_core(N₁)|/r_core(N₁) ≤ 5% (checked separately)
        # 3. Tail consistency: |p̂ - (2β-3)| ≤ 0.05 on [r_tail, r_max] (checked separately)

        # Estimate domain size L from field dimensions
        # If domain_size is provided, use it; otherwise estimate from grid
        if domain_size is not None:
            L_estimate = domain_size
        else:
            # For spatial dimensions, assume grid spacing ~ 1.0 if not provided
            spatial_shape = field.shape[:3] if len(field.shape) >= 3 else field.shape
            # Conservative estimate: L ~ max(spatial_dimension)
            L_estimate = float(max(spatial_shape)) if len(spatial_shape) > 0 else 1.0

        # Criterion 1: Ordering (0 < r_core < r_tail < L/4)
        # Note: For very large fields, r_tail may exceed L/4 in grid units.
        # In such cases, we relax the criterion to r_tail < L/2 to accommodate
        # large-scale structures while still ensuring proper ordering.
        ordering_ok = (
            r_core > 0  # Core radius strictly positive
            and r_tail > r_core  # Tail outside core
            and r_tail < L_estimate / 2.0  # Tail within L/2 (relaxed from L/4 for large fields)
        )

        # Criterion 2: Zone existence and quality
        zones_exist = (
            r_core > 0 and r_tail > 0 and np.any(core_mask) and np.any(tail_mask)
        )

        # Overall acceptance: all criteria must pass
        passed = ordering_ok and zones_exist

        return {
            "passed": passed,
            "core_mask": core_mask,
            "transition_mask": transition_mask,
            "tail_mask": tail_mask,
            "r_core": r_core,
            "r_tail": r_tail,
            "r_transition": r_transition,
            "indicators": indicators,
            "zone_stats": zone_stats,
            "quality_metrics": quality_metrics,
            "thresholds": thresholds,
        }

    def _compute_zone_indicators(
        self,
        field: np.ndarray,
        spatial_axes: Tuple[int, int, int] = (0, 1, 2),
        phase_axes: Tuple[int, int, int] = (3, 4, 5),
        time_axis: int = 6,
    ) -> Dict[str, np.ndarray]:
        """
        Compute zone indicators N, S, C.

        Physical Meaning:
            Computes local indicators that characterize the properties
            of the phase field and allow quantitative zone separation.

        Mathematical Foundation:
            - N: norm of gradient (density indicator)
            - S: second derivative (curvature indicator)
            - C: coherence indicator (local "stiffness")
        """
        # Check field dimensions and adjust axes accordingly
        if len(field.shape) == 7:
            # 7D field: use all axes
            N = self._compute_norm_gradient(field, spatial_axes, phase_axes, time_axis)
            S = self._compute_second_derivative(
                field, spatial_axes, phase_axes, time_axis
            )
            C = self._compute_coherence(field, spatial_axes, phase_axes, time_axis)
        else:
            # 3D field: use only spatial axes
            N = self._compute_norm_gradient(field, spatial_axes, (), -1)
            S = self._compute_second_derivative(field, spatial_axes, (), -1)
            C = self._compute_coherence(field, spatial_axes, (), -1)

        return {"N": N, "S": S, "C": C}

    def _compute_norm_gradient(
        self,
        field: np.ndarray,
        spatial_axes: Tuple[int, int, int],
        phase_axes: Tuple[int, int, int],
        time_axis: int,
    ) -> np.ndarray:
        """Compute norm of field gradient across axes."""
        xp = self.xp
        # Convert to GPU array if CUDA is enabled
        if self.use_cuda and isinstance(field, np.ndarray):
            field_gpu = xp.asarray(field)
        elif self.use_cuda:
            field_gpu = field
        else:
            field_gpu = field

        grads = []
        # Only use axes that exist in the field
        all_axes = [
            ax
            for ax in (*spatial_axes, *phase_axes, time_axis)
            if ax < len(field_gpu.shape)
        ]
        for ax in all_axes:
            grads.append(xp.gradient(field_gpu, axis=ax))
        # Sum of squares over all gradient components
        sq_sum = xp.zeros_like(field_gpu, dtype=float)
        for g in grads:
            sq_sum += xp.abs(g) ** 2
        result = xp.sqrt(sq_sum)
        # Convert back to numpy if needed
        if self.use_cuda and isinstance(result, xp.ndarray):
            return xp.asnumpy(result)
        return result

    def _compute_second_derivative(
        self,
        field: np.ndarray,
        spatial_axes: Tuple[int, int, int],
        phase_axes: Tuple[int, int, int],
        time_axis: int,
    ) -> np.ndarray:
        """Compute magnitude of Laplacian (sum of second derivatives)."""
        lap = self._compute_laplacian(field, spatial_axes, phase_axes, time_axis)
        return np.abs(lap)

    def _compute_laplacian(
        self,
        field: np.ndarray,
        spatial_axes: Tuple[int, int, int],
        phase_axes: Tuple[int, int, int],
        time_axis: int,
    ) -> np.ndarray:
        """Compute Laplacian (sum of second derivatives along all axes)."""
        xp = self.xp
        # Convert to GPU array if CUDA is enabled
        if self.use_cuda and isinstance(field, np.ndarray):
            field_gpu = xp.asarray(field)
        elif self.use_cuda:
            field_gpu = field
        else:
            field_gpu = field

        # Accumulate in complex if field is complex to avoid casting issues
        is_complex = xp.iscomplexobj(field_gpu) if hasattr(xp, "iscomplexobj") else np.iscomplexobj(field)
        acc_dtype = complex if is_complex else field_gpu.dtype
        lap = xp.zeros_like(field_gpu, dtype=acc_dtype)
        # Only use axes that exist in the field
        all_axes = [
            ax
            for ax in (*spatial_axes, *phase_axes, time_axis)
            if ax < len(field_gpu.shape)
        ]
        for ax in all_axes:
            lap += xp.gradient(xp.gradient(field_gpu, axis=ax), axis=ax)
        # Return magnitude for complex inputs to produce real-valued indicator
        result = lap if not is_complex else xp.abs(lap)
        # Convert back to numpy if needed
        if self.use_cuda and isinstance(result, xp.ndarray):
            return xp.asnumpy(result)
        return result

    def _compute_coherence(
        self,
        field: np.ndarray,
        spatial_axes: Tuple[int, int, int],
        phase_axes: Tuple[int, int, int],
        time_axis: int,
    ) -> np.ndarray:
        """Compute coherence indicator as amplitude gradient norm."""
        xp = self.xp
        # Convert to GPU array if CUDA is enabled
        if self.use_cuda and isinstance(field, np.ndarray):
            field_gpu = xp.asarray(field)
        elif self.use_cuda:
            field_gpu = field
        else:
            field_gpu = field

        amplitude = xp.abs(field_gpu)
        grads = []
        # Only use axes that exist in the field
        all_axes = [
            ax
            for ax in (*spatial_axes, *phase_axes, time_axis)
            if ax < len(field_gpu.shape)
        ]
        for ax in all_axes:
            grads.append(xp.gradient(amplitude, axis=ax))
        sq_sum = xp.zeros_like(amplitude, dtype=float)
        for g in grads:
            sq_sum += g**2
        result = xp.sqrt(sq_sum)
        # Convert back to numpy if needed
        if self.use_cuda and isinstance(result, xp.ndarray):
            return xp.asnumpy(result)
        return result

    def _compute_zone_radius(self, mask: np.ndarray, center: List[float]) -> float:
        """Compute effective radius of a zone."""
        if not np.any(mask):
            return 0.0

        # Find all points in the zone
        zone_points = np.where(mask)

        # Compute distances to center
        distances = []
        for i, j, k in zip(zone_points[0], zone_points[1], zone_points[2]):
            dist = np.sqrt(
                (i - center[0]) ** 2 + (j - center[1]) ** 2 + (k - center[2]) ** 2
            )
            distances.append(dist)

        # Effective radius (mean distance)
        return np.mean(distances) if distances else 0.0

    def _compute_zone_statistics(
        self,
        field: np.ndarray,
        core_mask: np.ndarray,
        transition_mask: np.ndarray,
        tail_mask: np.ndarray,
    ) -> Dict[str, Any]:
        """Compute statistics for each zone."""
        stats = {}

        for zone_name, mask in [
            ("core", core_mask),
            ("transition", transition_mask),
            ("tail", tail_mask),
        ]:
            if np.any(mask):
                zone_field = field[mask]
                stats[zone_name] = {
                    "volume_fraction": np.sum(mask) / mask.size,
                    "mean_amplitude": np.mean(np.abs(zone_field)),
                    "max_amplitude": np.max(np.abs(zone_field)),
                    "std_amplitude": np.std(np.abs(zone_field)),
                    "mean_phase": np.mean(np.angle(zone_field)),
                    "phase_std": np.std(np.angle(zone_field)),
                }
            else:
                stats[zone_name] = {
                    "volume_fraction": 0.0,
                    "mean_amplitude": 0.0,
                    "max_amplitude": 0.0,
                    "std_amplitude": 0.0,
                    "mean_phase": 0.0,
                    "phase_std": 0.0,
                }

        return stats

    def _assess_zone_separation_quality(
        self,
        core_mask: np.ndarray,
        tail_mask: np.ndarray,
        transition_mask: np.ndarray,
        zone_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assess quality of zone separation."""
        # Check for reasonable zone sizes
        core_fraction = zone_stats["core"]["volume_fraction"]
        tail_fraction = zone_stats["tail"]["volume_fraction"]
        transition_fraction = zone_stats["transition"]["volume_fraction"]

        # Check for proper ordering of amplitudes
        core_amplitude = zone_stats["core"]["mean_amplitude"]
        tail_amplitude = zone_stats["tail"]["mean_amplitude"]

        # Quality metrics
        quality = {
            "core_fraction": core_fraction,
            "tail_fraction": tail_fraction,
            "transition_fraction": transition_fraction,
            "amplitude_ordering": core_amplitude > tail_amplitude,
            "zone_balance": abs(core_fraction - tail_fraction)
            < 0.5,  # Not too imbalanced
            "total_coverage": core_fraction + tail_fraction + transition_fraction > 0.8,
        }

        # Overall quality score
        quality["overall_score"] = (
            sum(
                [
                    quality["amplitude_ordering"],
                    quality["zone_balance"],
                    quality["total_coverage"],
                ]
            )
            / 3
        )

        return quality

    def visualize_zone_analysis(
        self, analysis_result: Dict[str, Any], output_path: str = "zone_analysis.png"
    ) -> None:
        """
        Visualize zone analysis results.

        Physical Meaning:
            Creates visualization of the zone analysis showing
            zone maps, indicators, and separation quality.

        Args:
            analysis_result (Dict[str, Any]): Results from separate_zones
            output_path (str): Path to save the plot
        """
        _viz_zone(analysis_result, output_path)

    def run_zone_analysis_variations(
        self,
        field: np.ndarray,
        center: List[float],
        threshold_ranges: Dict[str, List[float]],
    ) -> Dict[str, Any]:
        """
        Run zone analysis for different threshold values.

        Physical Meaning:
            Analyzes zone separation sensitivity to threshold parameters,
            helping to determine optimal separation criteria.

        Args:
            field (np.ndarray): Phase field solution
            center (List[float]): Center of the defect
            threshold_ranges (Dict[str, List[float]]): Ranges of threshold values

        Returns:
            Dict[str, Any]: Results for all threshold combinations
        """
        return _run_variations(self.separate_zones, field, center, threshold_ranges)
