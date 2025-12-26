"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Zone properties analysis module for zone analysis.

This module implements zone properties analysis operations,
including statistical analysis of different zones in the BVP field.

Physical Meaning:
    Analyzes properties of different zones in the BVP field
    including amplitude, gradient, and coherence properties.

Mathematical Foundation:
    Computes statistical properties for each zone including
    mean, variance, and characteristic scales.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.bvp import BVPCore


class ZoneProperties:
    """
    Zone properties analysis for BVP field.

    Physical Meaning:
        Analyzes properties of different zones in the BVP field
        including amplitude, gradient, and coherence properties.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize zone properties analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def analyze_zone_properties(
        self, envelope: np.ndarray
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze properties of different zones.

        Physical Meaning:
            Analyzes properties of different zones in the BVP field
            including amplitude, gradient, and coherence properties.
        """
        amplitude = np.abs(envelope)

        # Define zone thresholds
        max_amplitude = np.max(amplitude)
        mean_amplitude = np.mean(amplitude)

        core_threshold = 0.8 * max_amplitude
        tail_threshold = 0.2 * mean_amplitude

        # Analyze core zones
        core_mask = amplitude > core_threshold
        core_properties = {
            "mean_amplitude": (
                np.mean(amplitude[core_mask]) if np.any(core_mask) else 0.0
            ),
            "variance": np.var(amplitude[core_mask]) if np.any(core_mask) else 0.0,
            "volume_fraction": np.sum(core_mask) / amplitude.size,
        }

        # Analyze transition zones
        transition_mask = ~(core_mask | (amplitude < tail_threshold))
        transition_properties = {
            "mean_amplitude": (
                np.mean(amplitude[transition_mask]) if np.any(transition_mask) else 0.0
            ),
            "variance": (
                np.var(amplitude[transition_mask]) if np.any(transition_mask) else 0.0
            ),
            "volume_fraction": np.sum(transition_mask) / amplitude.size,
        }

        # Analyze tail zones
        tail_mask = amplitude < tail_threshold
        tail_properties = {
            "mean_amplitude": (
                np.mean(amplitude[tail_mask]) if np.any(tail_mask) else 0.0
            ),
            "variance": np.var(amplitude[tail_mask]) if np.any(tail_mask) else 0.0,
            "volume_fraction": np.sum(tail_mask) / amplitude.size,
        }

        return {
            "core_properties": core_properties,
            "transition_properties": transition_properties,
            "tail_properties": tail_properties,
        }
