"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory utilities for Level C analysis.

This module implements utility functions for memory analysis
in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore


def calculate_memory_metrics(envelope: np.ndarray) -> Dict[str, float]:
    """
    Calculate memory metrics for the envelope field.

    Physical Meaning:
        Calculates various memory metrics including capacity,
        efficiency, and strength based on field properties.

    Mathematical Foundation:
        Uses information theory and correlation analysis
        to quantify memory properties.

    Args:
        envelope (np.ndarray): 7D envelope field data.

    Returns:
        Dict[str, float]: Dictionary of memory metrics.
    """
    metrics = {}

    # Calculate memory capacity
    metrics["capacity"] = _calculate_capacity(envelope)

    # Calculate memory efficiency
    metrics["efficiency"] = _calculate_efficiency(envelope)

    # Calculate memory strength
    metrics["strength"] = _calculate_strength(envelope)

    # Calculate memory persistence
    metrics["persistence"] = _calculate_persistence(envelope)

    return metrics


def analyze_memory_patterns(
    envelope: np.ndarray, threshold: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Analyze memory patterns in the envelope field.

    Physical Meaning:
        Analyzes memory patterns including temporal, spatial,
        and phase patterns that indicate memory effects.

    Args:
        envelope (np.ndarray): 7D envelope field data.
        threshold (float): Threshold for pattern detection.

    Returns:
        List[Dict[str, Any]]: List of detected memory patterns.
    """
    patterns = []

    # Analyze temporal patterns
    temporal_patterns = _analyze_temporal_patterns(envelope, threshold)
    patterns.extend(temporal_patterns)

    # Analyze spatial patterns
    spatial_patterns = _analyze_spatial_patterns(envelope, threshold)
    patterns.extend(spatial_patterns)

    # Analyze phase patterns
    phase_patterns = _analyze_phase_patterns(envelope, threshold)
    patterns.extend(phase_patterns)

    return patterns


def calculate_memory_interactions(
    envelope: np.ndarray, patterns: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate memory interactions between different patterns.

    Physical Meaning:
        Calculates interactions between different memory
        patterns, including coupling strength and interaction
        mechanisms.

    Args:
        envelope (np.ndarray): 7D envelope field data.
        patterns (List[Dict[str, Any]]): Detected memory patterns.

    Returns:
        Dict[str, Any]: Memory interaction analysis results.
    """
    interactions = {}

    # Calculate pattern interactions
    pattern_interactions = _calculate_pattern_interactions(patterns)
    interactions["pattern_interactions"] = pattern_interactions

    # Calculate field-pattern interactions
    field_interactions = _calculate_field_interactions(envelope, patterns)
    interactions["field_interactions"] = field_interactions

    # Calculate interaction strength
    interaction_strength = _calculate_interaction_strength(patterns)
    interactions["interaction_strength"] = interaction_strength

    return interactions


def validate_memory_analysis(results: Dict[str, Any]) -> bool:
    """
    Validate memory analysis results.

    Physical Meaning:
        Validates memory analysis results to ensure they
        are physically meaningful and mathematically consistent.

    Args:
        results (Dict[str, Any]): Memory analysis results.

    Returns:
        bool: True if results are valid, False otherwise.
    """
    # Check for required keys
    required_keys = ["memory_capacity", "persistence_patterns", "memory_strength"]
    for key in required_keys:
        if key not in results:
            return False

    # Validate memory capacity
    capacity = results["memory_capacity"]
    if not isinstance(capacity, (int, float)) or capacity < 0:
        return False

    # Validate persistence patterns
    patterns = results["persistence_patterns"]
    if not isinstance(patterns, list):
        return False

    # Validate memory strength
    strength = results["memory_strength"]
    if not isinstance(strength, (int, float)) or strength < 0:
        return False

    return True


def _calculate_capacity(envelope: np.ndarray) -> float:
    """Calculate memory capacity from field properties."""
    # Calculate capacity based on field variance and correlation
    field_variance = np.var(envelope)
    field_mean = np.mean(envelope)

    # Capacity is proportional to variance and mean
    capacity = field_variance * abs(field_mean)

    return float(capacity)


def _calculate_efficiency(envelope: np.ndarray) -> float:
    """Calculate memory efficiency from field properties."""
    # Calculate efficiency based on field smoothness
    field_gradient = np.gradient(envelope)
    gradient_magnitude = np.sqrt(sum(g**2 for g in field_gradient))

    # Efficiency is inversely proportional to gradient magnitude
    efficiency = 1.0 / (1.0 + np.mean(gradient_magnitude))

    return float(efficiency)


def _calculate_strength(envelope: np.ndarray) -> float:
    """Calculate memory strength from field properties."""
    # Calculate strength based on field amplitude and persistence
    field_amplitude = np.max(np.abs(envelope))
    field_persistence = np.corrcoef(envelope.flatten(), envelope.flatten())[0, 1]

    # Strength is proportional to amplitude and persistence
    strength = field_amplitude * abs(field_persistence)

    return float(strength)


def _calculate_persistence(envelope: np.ndarray) -> float:
    """Calculate memory persistence from field properties."""
    # Calculate persistence based on temporal correlation
    if envelope.ndim > 1:
        # Calculate correlation between consecutive time steps
        time_correlation = np.corrcoef(envelope[0].flatten(), envelope[-1].flatten())[
            0, 1
        ]
    else:
        time_correlation = 1.0

    # Persistence is the absolute value of time correlation
    persistence = abs(time_correlation)

    return float(persistence)


def _analyze_temporal_patterns(
    envelope: np.ndarray, threshold: float
) -> List[Dict[str, Any]]:
    """Analyze temporal memory patterns."""
    patterns = []

    # Calculate temporal correlation
    if envelope.ndim > 1:
        temporal_corr = np.corrcoef(envelope.reshape(-1, envelope.shape[-1]))

        # Find patterns above threshold
        for i in range(len(temporal_corr)):
            for j in range(i + 1, len(temporal_corr)):
                if abs(temporal_corr[i, j]) > threshold:
                    patterns.append(
                        {
                            "type": "temporal",
                            "strength": float(temporal_corr[i, j]),
                            "indices": (i, j),
                            "pattern": temporal_corr[i, j],
                        }
                    )

    return patterns


def _analyze_spatial_patterns(
    envelope: np.ndarray, threshold: float
) -> List[Dict[str, Any]]:
    """Analyze spatial memory patterns."""
    patterns = []

    # Calculate spatial correlation
    if envelope.ndim > 1:
        spatial_corr = np.corrcoef(envelope.reshape(envelope.shape[0], -1))

        # Find patterns above threshold
        for i in range(len(spatial_corr)):
            for j in range(i + 1, len(spatial_corr)):
                if abs(spatial_corr[i, j]) > threshold:
                    patterns.append(
                        {
                            "type": "spatial",
                            "strength": float(spatial_corr[i, j]),
                            "indices": (i, j),
                            "pattern": spatial_corr[i, j],
                        }
                    )

    return patterns


def _analyze_phase_patterns(
    envelope: np.ndarray, threshold: float
) -> List[Dict[str, Any]]:
    """Analyze phase memory patterns."""
    patterns = []

    # Calculate phase correlation
    if envelope.ndim > 1:
        phase_indices = [3, 4, 5]  # Phase dimensions
        phase_data = envelope.take(phase_indices, axis=0)
        phase_corr = np.corrcoef(phase_data.reshape(phase_data.shape[0], -1))

        # Find patterns above threshold
        for i in range(len(phase_corr)):
            for j in range(i + 1, len(phase_corr)):
                if abs(phase_corr[i, j]) > threshold:
                    patterns.append(
                        {
                            "type": "phase",
                            "strength": float(phase_corr[i, j]),
                            "indices": (i, j),
                            "pattern": phase_corr[i, j],
                        }
                    )

    return patterns


def _calculate_pattern_interactions(patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate interactions between different patterns."""
    interactions = {}

    # Calculate interaction strength between patterns
    if len(patterns) > 1:
        interaction_strength = 0.0
        for i in range(len(patterns)):
            for j in range(i + 1, len(patterns)):
                pattern_i = patterns[i]
                pattern_j = patterns[j]

                # Calculate interaction strength
                strength = pattern_i["strength"] * pattern_j["strength"]
                interaction_strength += strength

        interactions["total_interaction_strength"] = interaction_strength
        interactions["average_interaction_strength"] = interaction_strength / (
            len(patterns) * (len(patterns) - 1) / 2
        )
    else:
        interactions["total_interaction_strength"] = 0.0
        interactions["average_interaction_strength"] = 0.0

    return interactions


def _calculate_field_interactions(
    envelope: np.ndarray, patterns: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate interactions between field and patterns."""
    interactions = {}

    # Calculate field-pattern interaction strength
    field_strength = np.max(np.abs(envelope))
    pattern_strength = sum(pattern["strength"] for pattern in patterns)

    interactions["field_pattern_interaction"] = field_strength * pattern_strength
    interactions["field_strength"] = field_strength
    interactions["pattern_strength"] = pattern_strength

    return interactions


def _calculate_interaction_strength(patterns: List[Dict[str, Any]]) -> float:
    """Calculate overall interaction strength."""
    if not patterns:
        return 0.0

    # Calculate interaction strength based on pattern strengths
    total_strength = sum(pattern["strength"] for pattern in patterns)
    interaction_strength = total_strength / len(patterns)

    return float(interaction_strength)
