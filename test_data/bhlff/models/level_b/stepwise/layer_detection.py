"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Layer detection for stepwise power law analysis.

This module implements methods for detecting discrete layers in stepwise
structures, supporting both field and substrate analysis.

Theoretical Background:
    In 7D BVP theory, the field exhibits stepwise structure with discrete
    layers R₀ < R₁ < R₂ < ... representing quantized spatial regions
    with distinct properties.

Example:
    >>> detector = LayerDetector(use_cuda=True)
    >>> layers = detector.detect_layers(field, center)
"""

import numpy as np
from typing import Dict, Any, List
import logging

# CUDA support
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class LayerDetector:
    """
    Layer detection for stepwise structure analysis.

    Physical Meaning:
        Detects discrete layers R₀ < R₁ < R₂ < ... in stepwise structures,
        identifying quantized spatial regions with distinct field properties.

    Mathematical Foundation:
        Layer boundaries are identified through gradient analysis and
        quantized spacing patterns, representing the fundamental stepwise
        behavior of fractional Laplacian solutions.
    """

    def __init__(self, use_cuda: bool = True):
        """
        Initialize layer detector.

        Physical Meaning:
            Sets up detector for identifying discrete layers in stepwise
            structures with CUDA acceleration support.

        Args:
            use_cuda (bool): Whether to use CUDA acceleration.
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        self.logger = logging.getLogger(__name__)

        if self.use_cuda:
            self.xp = cp
        else:
            self.xp = np

    def detect_layers(
        self,
        field: np.ndarray,
        center: List[float],
        radial_profile: Dict[str, np.ndarray],
    ) -> List[Dict[str, Any]]:
        """
        Detect discrete layers R₀ < R₁ < R₂ < ... in stepwise structure.

        Physical Meaning:
            Identifies discrete layers with quantized radii according to
            7D BVP theory: Θ(r) = Σₙ≥₀ θₙ(r), θₙ поддержана в [Rₙ,Rₙ₊₁]

        Args:
            field (np.ndarray): Phase field solution.
            center (List[float]): Center of the defect [x, y, z].
            radial_profile (Dict[str, np.ndarray]): Pre-computed radial profile.

        Returns:
            List[Dict[str, Any]]: List of detected layers with boundaries and data.
        """
        if self.use_cuda:
            gradient = self.xp.gradient(radial_profile["A"], radial_profile["r"])
            second_derivative = self.xp.gradient(gradient, radial_profile["r"])
        else:
            gradient = np.gradient(radial_profile["A"], radial_profile["r"])
            second_derivative = np.gradient(gradient, radial_profile["r"])

        layer_boundary_indices = self._find_layer_boundaries(
            gradient, second_derivative
        )

        if self.use_cuda:
            layer_boundaries = self.xp.asnumpy(
                radial_profile["r"][layer_boundary_indices]
            )
            r_array = self.xp.asnumpy(radial_profile["r"])
            A_array = self.xp.asnumpy(radial_profile["A"])
        else:
            layer_boundaries = radial_profile["r"][layer_boundary_indices]
            r_array = radial_profile["r"]
            A_array = radial_profile["A"]

        layers = []
        for i in range(len(layer_boundaries) - 1):
            r_start = layer_boundaries[i]
            r_end = layer_boundaries[i + 1]

            layer_mask = (r_array >= r_start) & (r_array < r_end)

            layer_data = {
                "r_start": float(r_start),
                "r_end": float(r_end),
                "amplitude": A_array[layer_mask],
                "radius": r_array[layer_mask],
                "layer_index": i,
            }
            layers.append(layer_data)

        return layers

    def detect_substrate_layers(
        self,
        substrate: np.ndarray,
        center: List[float],
        radial_profile: Dict[str, np.ndarray],
    ) -> List[Dict[str, Any]]:
        """
        Detect discrete layers in substrate based on transparency changes.

        Physical Meaning:
            Identifies discrete layers in the substrate where transparency
            changes significantly, representing resonator walls and boundaries.

        Args:
            substrate (np.ndarray): 7D substrate field (transparency/permeability).
            center (List[float]): Center coordinates [x, y, z].
            radial_profile (Dict[str, np.ndarray]): Pre-computed radial profile.

        Returns:
            List[Dict[str, Any]]: List of detected layers with radii and properties.
        """
        r = radial_profile["r"]
        T = radial_profile["A"]

        if len(r) < 3:
            return []

        T_diff = np.abs(np.diff(T))
        if len(T_diff) == 0:
            return []

        threshold = np.mean(T_diff) + 0.5 * np.std(T_diff)
        significant_changes = T_diff > threshold
        change_indices = np.where(significant_changes)[0]

        if len(change_indices) == 0:
            return self._build_quantile_layers(r, T)

        layer_boundaries = r[change_indices]
        layers = []
        for i, boundary in enumerate(layer_boundaries):
            if i == 0:
                r_start = 0.0
            else:
                r_start = layer_boundaries[i - 1]

            if i == len(layer_boundaries) - 1:
                r_end = r[-1]
            else:
                r_end = layer_boundaries[i + 1]

            mask = (r >= r_start) & (r < r_end)
            if np.any(mask):
                avg_transparency = np.mean(T[mask])
                layer_radius = (r_start + r_end) / 2

                layers.append(
                    {
                        "r_start": r_start,
                        "r_end": r_end,
                        "radius": np.array([layer_radius]),
                        "amplitude": np.array([avg_transparency]),
                        "layer_index": i,
                    }
                )

        return layers

    def build_quantile_layers(
        self,
        radial_profile: Dict[str, np.ndarray],
        target_layers: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Build quantile-based layers from radial profile.

        Physical Meaning:
            Constructs layers based on quantile partitioning of amplitude,
            providing robust fallback when gradient-based detection fails.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.
            target_layers (int): Target number of layers.

        Returns:
            List[Dict[str, Any]]: List of quantile-based layers.
        """
        r = radial_profile["r"]
        T = radial_profile["A"]

        if len(r) < target_layers:
            return []

        q_edges = np.quantile(T, np.linspace(0.0, 1.0, target_layers + 1))
        layers = []
        for i in range(target_layers):
            mask = (T >= q_edges[i]) & (T <= q_edges[i + 1])
            if np.any(mask):
                r_values = r[mask]
                r_start = float(np.min(r_values))
                r_end = float(np.max(r_values))
                layer_radius = (r_start + r_end) / 2.0
                avg_amp = float(np.mean(T[mask]))
                layers.append(
                    {
                        "r_start": r_start,
                        "r_end": r_end,
                        "radius": np.array([layer_radius]),
                        "amplitude": np.array([avg_amp]),
                        "layer_index": i,
                    }
                )
        return layers

    def build_uniform_layers(
        self,
        radial_profile: Dict[str, np.ndarray],
        segments: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Build uniformly partitioned radial layers.

        Physical Meaning:
            Constructs layers by uniform radial partitioning as a last-resort
            fallback when other detection methods fail.

        Args:
            radial_profile (Dict[str, np.ndarray]): Radial profile data.
            segments (int): Number of uniform segments.

        Returns:
            List[Dict[str, Any]]: List of uniformly partitioned layers.
        """
        r = radial_profile["r"]
        T = radial_profile["A"]

        if len(r) < segments:
            return []

        r_edges = np.linspace(r.min(), r.max(), segments + 1)
        layers = []
        for i in range(segments):
            mask = (r >= r_edges[i]) & (r <= r_edges[i + 1])
            if np.any(mask):
                r_start = float(r_edges[i])
                r_end = float(r_edges[i + 1])
                layer_radius = (r_start + r_end) / 2.0
                avg_amp = float(np.mean(T[mask]))
                layers.append(
                    {
                        "r_start": r_start,
                        "r_end": r_end,
                        "radius": np.array([layer_radius]),
                        "amplitude": np.array([avg_amp]),
                        "layer_index": i,
                    }
                )
        return layers

    def _find_layer_boundaries(
        self, gradient: np.ndarray, second_derivative: np.ndarray
    ) -> np.ndarray:
        """
        Find layer boundaries using gradient analysis.

        Physical Meaning:
            Identifies significant transitions in gradient that correspond
            to layer boundaries in stepwise structure.

        Args:
            gradient (np.ndarray): Gradient of radial profile.
            second_derivative (np.ndarray): Second derivative of radial profile.

        Returns:
            np.ndarray: Array of layer boundary indices.
        """
        gradient_changes = self.xp.abs(self.xp.diff(gradient))
        threshold = self.xp.std(gradient_changes) * 1.5
        significant_changes = gradient_changes > threshold
        boundary_indices = self.xp.where(significant_changes)[0]

        boundaries = self.xp.concatenate(
            [self.xp.array([0]), boundary_indices, self.xp.array([len(gradient) - 1])]
        )

        if self.use_cuda:
            return self.xp.asnumpy(boundaries)
        else:
            return boundaries

    def _build_quantile_layers(
        self, r: np.ndarray, T: np.ndarray
    ) -> List[Dict[str, Any]]:
        """
        Internal helper to build quantile layers from arrays.

        Args:
            r (np.ndarray): Radius array.
            T (np.ndarray): Transparency/amplitude array.

        Returns:
            List[Dict[str, Any]]: List of quantile-based layers.
        """
        q_edges = np.quantile(T, [0.0, 0.33, 0.66, 1.0])
        layers = []
        for i in range(3):
            mask = (T >= q_edges[i]) & (T <= q_edges[i + 1])
            if np.any(mask):
                r_values = r[mask]
                r_start = float(np.min(r_values))
                r_end = float(np.max(r_values))
                layer_radius = (r_start + r_end) / 2.0
                avg_amp = float(np.mean(T[mask]))
                layers.append(
                    {
                        "r_start": r_start,
                        "r_end": r_end,
                        "radius": np.array([layer_radius]),
                        "amplitude": np.array([avg_amp]),
                        "layer_index": i,
                    }
                )
        return layers
