"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Geometric decay analysis for stepwise power law analysis.

This module implements methods for analyzing geometric decay factors
and radius quantization in stepwise structures.

Theoretical Background:
    In 7D BVP theory, geometric decay ensures that each layer has smaller
    gradient norm than the previous layer by factor q ∈ (0,1), and layer
    boundaries follow quantized spacing patterns.

Example:
    >>> analyzer = GeometricDecayAnalyzer()
    >>> q_factors = analyzer.compute_decay_factors(layers)
    >>> quantization = analyzer.check_quantization(layers)
"""

import numpy as np
from typing import Dict, Any, List


class GeometricDecayAnalyzer:
    """
    Geometric decay and quantization analysis.

    Physical Meaning:
        Analyzes geometric decay factors q between discrete layers and
        verifies quantized spacing of layer boundaries in stepwise structures.

    Mathematical Foundation:
        Geometric decay: ||∇θₙ₊₁|| ≤ q ||∇θₙ|| for q ∈ (0,1)
        Quantization: Layer boundaries follow discrete spacing patterns
        with approximately constant ratios.
    """

    def __init__(self, eps: float = 1e-15, quantization_tolerance: float = 0.1):
        """
        Initialize geometric decay analyzer.

        Physical Meaning:
            Sets up analyzer with numerical stability parameters for
            computing decay factors and quantization metrics.

        Args:
            eps (float): Numerical stability epsilon.
            quantization_tolerance (float): Tolerance for quantization check.
        """
        self.eps = eps
        self.quantization_tolerance = quantization_tolerance

    def compute_decay_factors(self, layers: List[Dict[str, Any]]) -> List[float]:
        """
        Compute geometric decay factors q between layers.

        Physical Meaning:
            Computes ||∇θₙ₊₁|| ≤ q ||∇θₙ|| for geometric decay
            between discrete layers in stepwise structure.

        Mathematical Foundation:
            Geometric decay ensures that each layer has smaller
            gradient norm than the previous layer by factor q ∈ (0,1).

        Args:
            layers (List[Dict[str, Any]]): List of detected layers.

        Returns:
            List[float]: Geometric decay factors q between adjacent layers.
        """
        if len(layers) < 2:
            return []

        mean_amplitudes = np.array(
            [
                np.mean(layer["amplitude"]) if len(layer["amplitude"]) > 0 else 0.0
                for layer in layers
            ]
        )

        valid_mask = mean_amplitudes[:-1] > self.eps
        q_factors_array = np.where(
            valid_mask, mean_amplitudes[1:] / mean_amplitudes[:-1], 0.0
        )

        q_factors = [
            float(q) for q in q_factors_array[valid_mask] if q > self.eps and q < 1.0
        ]

        return q_factors

    def check_quantization(self, layers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check radius quantization in discrete layers.

        Physical Meaning:
            Verifies that layer boundaries follow quantized pattern
            R₀ < R₁ < R₂ < ... with discrete spacing.

        Mathematical Foundation:
            Quantized spacing ensures that layer boundaries follow
            discrete pattern with approximately constant ratios.

        Args:
            layers (List[Dict[str, Any]]): List of detected layers.

        Returns:
            Dict[str, Any]: Quantization analysis results.
        """
        if len(layers) < 2:
            return {"quantized": False, "spacing_ratio": None}

        boundaries = [layer["r_start"] for layer in layers]
        boundaries.append(layers[-1]["r_end"])

        boundaries_array = np.array(boundaries)
        if len(boundaries_array) >= 3:
            diffs_1 = boundaries_array[1:-1] - boundaries_array[:-2]
            diffs_2 = boundaries_array[2:] - boundaries_array[1:-1]
            valid_mask = diffs_1 > self.eps
            spacing_ratios = (diffs_2[valid_mask] / diffs_1[valid_mask]).tolist()
        else:
            spacing_ratios = []

        if len(spacing_ratios) > 0:
            mean_ratio = np.mean(spacing_ratios)
            std_ratio = np.std(spacing_ratios)
            quantized = std_ratio / mean_ratio < self.quantization_tolerance
        else:
            quantized = False
            mean_ratio = None

        return {
            "quantized": quantized,
            "spacing_ratio": mean_ratio,
            "spacing_ratios": spacing_ratios,
            "tolerance": self.quantization_tolerance,
        }
