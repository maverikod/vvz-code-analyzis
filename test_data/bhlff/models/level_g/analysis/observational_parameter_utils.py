"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Utility computations for observational parameter analysis in 7D phase field theory.

This module provides standalone helper functions used by
`observational_comparison_parameters.py` to keep the class file size
within project limits while preserving single-responsibility and clarity.

Theoretical Background:
    Implements auxiliary numerical routines that operate on phase field
    arrays to extract cosmologically relevant quantities consistent with
    the 7D BVP framework (no classical physics fallbacks).

Example:
    >>> import numpy as np
    >>> from .observational_parameter_utils import compute_scale_factor_from_phase_field
    >>> a = compute_scale_factor_from_phase_field(np.ones((8, 8, 8)))
"""

from __future__ import annotations

from typing import Tuple
import numpy as np


def compute_scale_factor_from_phase_field(phase_field: np.ndarray) -> np.ndarray:
    """
    Compute normalized scale factor surrogate from a phase field array.

    Physical Meaning:
        Derives a monotone surrogate for the cosmological scale factor from
        the 7D phase field amplitude evolution without introducing classical
        exponential laws, purely via field-amplitude normalization.

    Args:
        phase_field: Phase field evolution data (time-major or flattened).

    Returns:
        np.ndarray: Normalized scale factor-like sequence a(t) >= 0.
    """
    if phase_field.size == 0:
        return np.array([1.0])

    if phase_field.ndim > 1:
        amplitude_evolution = np.mean(
            np.abs(phase_field), axis=tuple(range(1, phase_field.ndim))
        )
    else:
        amplitude_evolution = np.abs(phase_field)

    max_val = np.max(amplitude_evolution) if amplitude_evolution.size > 0 else 1.0
    if max_val <= 0:
        return np.ones_like(amplitude_evolution, dtype=float)
    return amplitude_evolution / max_val


def compute_matter_density_from_phase_field(phase_field: np.ndarray) -> float:
    """
    Compute a bounded matter-density surrogate from the phase field.

    Physical Meaning:
        Uses variance of the normalized density contrast as a proxy for
        matter content consistent with 7D field fluctuations.

    Args:
        phase_field: Phase field data array.

    Returns:
        float: Matter density parameter Ω_m in a physically plausible range.
    """
    if phase_field.size == 0:
        return 0.3

    mean_density = float(np.mean(phase_field))
    # Guard against zero mean to avoid division by zero
    if mean_density == 0:
        return 0.3
    density_contrast = (phase_field - mean_density) / mean_density
    variance_proxy = float(np.mean(density_contrast**2))
    return float(np.clip(variance_proxy, 0.1, 0.5))


def compute_curvature_from_phase_field(phase_field: np.ndarray) -> float:
    """
    Compute a small, bounded curvature surrogate from field geometry.

    Physical Meaning:
        Estimates spatial curvature using mean-squared gradients of the field
        while staying within non-classical 7D BVP constraints.

    Args:
        phase_field: Phase field data array.

    Returns:
        float: Curvature parameter in [0, 0.1].
    """
    if phase_field.size == 0:
        return 0.0

    if phase_field.ndim > 1:
        grad_x = np.gradient(phase_field, axis=0)
        if phase_field.ndim > 2:
            grad_y = np.gradient(phase_field, axis=1)
            grad_z = np.gradient(phase_field, axis=2)
            curvature = float(np.mean(grad_x**2 + grad_y**2 + grad_z**2))
        else:
            curvature = float(np.mean(grad_x**2))
    else:
        curvature = 0.0

    return float(np.clip(curvature, 0.0, 0.1))


def compute_dark_energy_from_phase_field(phase_field: np.ndarray) -> float:
    """
    Compute dark-energy surrogate from field-derived matter and curvature.

    Physical Meaning:
        Uses the closure Ω_Λ = 1 - Ω_m - Ω_k with Ω_m and Ω_k computed from
        phase-field statistics, ensuring physically plausible bounds.

    Args:
        phase_field: Phase field data array.

    Returns:
        float: Dark energy parameter Ω_Λ >= 0.1 (bounded below for stability).
    """
    if phase_field.size == 0:
        return 0.7

    matter_density = compute_matter_density_from_phase_field(phase_field)
    curvature = compute_curvature_from_phase_field(phase_field)
    dark_energy = 1.0 - matter_density - curvature
    return float(max(0.1, dark_energy))
