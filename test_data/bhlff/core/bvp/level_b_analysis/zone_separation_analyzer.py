"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Zone separation analyzer for Level B BVP interface.

This module implements analysis of separation of core/transition/tail zones
in the BVP envelope for the Level B BVP interface, identifying the three
characteristic zones according to the theory.

Physical Meaning:
    Identifies the three characteristic zones in the BVP envelope:
    core (high amplitude, nonlinear), transition (intermediate),
    and tail (low amplitude, linear) regions according to the 7D
    phase field theory.

Mathematical Foundation:
    Analyzes radial amplitude profile to identify zone boundaries
    based on amplitude thresholds and computes zone indicators
    (N, S, C) representing nonlinearity, scale separation, and coherence.

Example:
    >>> analyzer = ZoneSeparationAnalyzer()
    >>> zones_data = analyzer.analyze_zone_separation(envelope)
"""

import numpy as np
from typing import Dict, Any


class ZoneSeparationAnalyzer:
    """
    Zone separation analyzer for Level B BVP interface.

    Physical Meaning:
        Identifies the three characteristic zones in the BVP envelope:
        core (high amplitude, nonlinear), transition (intermediate),
        and tail (low amplitude, linear) regions according to the 7D
        phase field theory.

    Mathematical Foundation:
        Analyzes radial amplitude profile to identify zone boundaries
        based on amplitude thresholds and computes zone indicators
        (N, S, C) representing nonlinearity, scale separation, and coherence.
    """

    def analyze_zone_separation(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze separation of core/transition/tail zones.

        Physical Meaning:
            Identifies the three characteristic zones in the BVP envelope:
            core (high amplitude, nonlinear), transition (intermediate),
            and tail (low amplitude, linear) regions.

        Mathematical Foundation:
            Analyzes radial amplitude profile to identify zone boundaries
            and computes zone indicators (N, S, C) from theory.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - core_radius: Normalized core zone radius
                - transition_radius: Normalized transition zone radius
                - tail_radius: Normalized tail zone radius
                - zone_indicators: Dictionary with N, S, C indicators
        """
        amplitude = np.abs(envelope)

        # Compute radial profile from center
        center = np.array(amplitude.shape) // 2
        x, y, z = np.meshgrid(
            np.arange(amplitude.shape[0]) - center[0],
            np.arange(amplitude.shape[1]) - center[1],
            np.arange(amplitude.shape[2]) - center[2],
            indexing="ij",
        )
        r = np.sqrt(x**2 + y**2 + z**2)

        # Find maximum radius
        r_max = np.max(r)

        # Compute radial average
        r_bins = np.linspace(0, r_max, 50)
        radial_profile = []
        for i in range(len(r_bins) - 1):
            mask = (r >= r_bins[i]) & (r < r_bins[i + 1])
            if np.sum(mask) > 0:
                radial_profile.append(np.mean(amplitude[mask]))
            else:
                radial_profile.append(0.0)

        radial_profile = np.array(radial_profile)
        r_centers = (r_bins[:-1] + r_bins[1:]) / 2

        # Find zone boundaries based on amplitude thresholds
        max_amplitude = np.max(radial_profile)

        # Core zone: amplitude > 0.5 * max
        core_threshold = 0.5 * max_amplitude
        core_mask = radial_profile > core_threshold
        if np.any(core_mask):
            core_radius = r_centers[core_mask][-1] / r_max  # Last point above threshold
        else:
            core_radius = 0.1

        # Transition zone: 0.1 * max < amplitude < 0.5 * max
        transition_low = 0.1 * max_amplitude
        transition_high = 0.5 * max_amplitude
        transition_mask = (radial_profile > transition_low) & (
            radial_profile < transition_high
        )
        if np.any(transition_mask):
            transition_radius = r_centers[transition_mask][-1] / r_max
        else:
            transition_radius = 0.3

        # Tail zone: amplitude < 0.1 * max
        tail_threshold = 0.1 * max_amplitude
        tail_mask = radial_profile < tail_threshold
        if np.any(tail_mask):
            tail_radius = r_centers[tail_mask][0] / r_max  # First point below threshold
        else:
            tail_radius = 1.0

        # Compute zone indicators (N, S, C from theory)
        # N: Nonlinearity parameter in core
        core_region = r < core_radius * r_max
        if np.sum(core_region) > 0:
            core_amplitude = np.mean(amplitude[core_region])
            N = core_amplitude / max_amplitude if max_amplitude > 0 else 0.0
        else:
            N = 0.0

        # S: Scale separation parameter
        S = core_radius / transition_radius if transition_radius > 0 else 1.0

        # C: Coherence parameter
        C = transition_radius / tail_radius if tail_radius > 0 else 1.0

        return {
            "core_radius": float(core_radius),
            "transition_radius": float(transition_radius),
            "tail_radius": float(tail_radius),
            "zone_indicators": {"N": float(N), "S": float(S), "C": float(C)},
        }

    def compute_zone_statistics(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute detailed statistics for each zone.

        Physical Meaning:
            Computes detailed statistical properties of each zone
            to characterize their physical properties.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing zone statistics.
        """
        amplitude = np.abs(envelope)

        # Get zone boundaries
        zone_data = self.analyze_zone_separation(envelope)
        core_radius = zone_data["core_radius"]
        transition_radius = zone_data["transition_radius"]
        tail_radius = zone_data["tail_radius"]

        # Compute radial profile
        center = np.array(amplitude.shape) // 2
        x, y, z = np.meshgrid(
            np.arange(amplitude.shape[0]) - center[0],
            np.arange(amplitude.shape[1]) - center[1],
            np.arange(amplitude.shape[2]) - center[2],
            indexing="ij",
        )
        r = np.sqrt(x**2 + y**2 + z**2)
        r_max = np.max(r)

        # Define zones
        core_region = r < core_radius * r_max
        transition_region = (r >= core_radius * r_max) & (r < transition_radius * r_max)
        tail_region = r >= tail_radius * r_max

        # Compute zone statistics
        core_stats = self._compute_region_statistics(amplitude, core_region)
        transition_stats = self._compute_region_statistics(amplitude, transition_region)
        tail_stats = self._compute_region_statistics(amplitude, tail_region)

        return {
            "core_zone": core_stats,
            "transition_zone": transition_stats,
            "tail_zone": tail_stats,
        }

    def _compute_region_statistics(
        self, amplitude: np.ndarray, region_mask: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compute statistics for a specific region.

        Args:
            amplitude (np.ndarray): Field amplitude.
            region_mask (np.ndarray): Boolean mask for the region.

        Returns:
            Dict[str, Any]: Statistics for the region.
        """
        if np.sum(region_mask) == 0:
            return {
                "mean_amplitude": 0.0,
                "std_amplitude": 0.0,
                "max_amplitude": 0.0,
                "volume_fraction": 0.0,
            }

        region_amplitude = amplitude[region_mask]

        return {
            "mean_amplitude": float(np.mean(region_amplitude)),
            "std_amplitude": float(np.std(region_amplitude)),
            "max_amplitude": float(np.max(region_amplitude)),
            "volume_fraction": float(np.sum(region_mask) / region_mask.size),
        }
