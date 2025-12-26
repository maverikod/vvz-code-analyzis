"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scaling functions and region identification for 7D critical analysis.

Provides reusable routines for computing correlation, susceptibility,
and order parameter scaling functions, and detecting critical regions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import numpy as np


def compute_correlation_scaling_function(
    bvp_core: Any, amplitude: np.ndarray, critical_exponents: Dict[str, float]
) -> Dict[str, Any]:
    """
    Compute correlation scaling function.

    Returns average correlation length and related exponents.
    """
    from .correlation_analysis import CorrelationAnalysis

    nu = critical_exponents.get("nu", 0.5)
    eta = critical_exponents.get("eta", 0.0)

    correlation_analyzer = CorrelationAnalysis(bvp_core)
    correlation_7d = correlation_analyzer._compute_7d_correlation_function(amplitude)
    correlation_lengths = correlation_analyzer._compute_7d_correlation_lengths(
        correlation_7d
    )
    avg_correlation_length = np.mean(list(correlation_lengths.values()))

    return {
        "correlation_length": float(avg_correlation_length),
        "scaling_exponent": float(nu),
        "anomalous_dimension": float(eta),
    }


def compute_susceptibility_scaling_function(
    amplitude: np.ndarray, critical_exponents: Dict[str, float]
) -> Dict[str, Any]:
    """
    Compute susceptibility scaling function.
    """
    gamma = critical_exponents.get("gamma", 1.0)
    variance = np.var(amplitude)
    mean_amp = np.mean(amplitude)
    susceptibility = variance / mean_amp if mean_amp > 0 else 0.0
    return {"susceptibility": float(susceptibility), "scaling_exponent": float(gamma)}


def compute_order_parameter_scaling_function(
    amplitude: np.ndarray, critical_exponents: Dict[str, float]
) -> Dict[str, Any]:
    """
    Compute order parameter scaling function.
    """
    beta = critical_exponents.get("beta", 0.5)
    order_parameter = np.mean(amplitude)
    return {"order_parameter": float(order_parameter), "scaling_exponent": float(beta)}


def identify_critical_regions(
    amplitude: np.ndarray, critical_exponents: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Identify critical regions with scaling analysis.
    """
    critical_regions: List[Dict[str, Any]] = []
    threshold = np.mean(amplitude) + 2 * np.std(amplitude)
    critical_mask = amplitude > threshold
    if np.any(critical_mask):
        from scipy import ndimage

        labeled_regions, num_regions = ndimage.label(critical_mask)
        for region_id in range(1, num_regions + 1):
            region_mask = labeled_regions == region_id
            region_coords = np.where(region_mask)
            if len(region_coords[0]) > 0:
                region_amplitude = amplitude[region_mask]
                region_center: Tuple[float, ...] = tuple(
                    np.mean(coords) for coords in region_coords
                )
                region_size = int(np.sum(region_mask))
                critical_regions.append(
                    {
                        "center": region_center,
                        "size": region_size,
                        "mean_amplitude": float(np.mean(region_amplitude)),
                        "amplitude_variance": float(np.var(region_amplitude)),
                        "critical_exponents": critical_exponents,
                        "scaling_behavior": "critical",
                    }
                )
    return critical_regions
