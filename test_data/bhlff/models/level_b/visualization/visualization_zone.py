"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Zone analysis visualization for Level B.
"""

import matplotlib.pyplot as plt
from typing import Dict, Any
from pathlib import Path


class LevelBVisualizerZone:
    """
    Zone analysis visualization for Level B.

    Physical Meaning:
        Creates visualizations for zone separation analysis results,
        showing zone radii, fractions, and quality metrics.
    """

    def visualize_zone_analysis(
        self, result: Dict[str, Any], output_path: Path
    ) -> None:
        """Visualize zone separation analysis results."""
        if not result.get("passed", False):
            return

        zone_result = result.get("zone_result", {})
        if not zone_result:
            return

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

        # Plot 1: Zone radii
        r_core = zone_result.get("r_core", 0)
        r_tail = zone_result.get("r_tail", 0)
        r_transition = zone_result.get("r_transition", 0)

        zones = ["Core", "Transition", "Tail"]
        radii = [r_core, r_transition, r_tail]
        colors = ["red", "yellow", "blue"]

        ax1.bar(zones, radii, color=colors, alpha=0.7)
        ax1.set_ylabel("Radius")
        ax1.set_title("Zone Radii")
        ax1.grid(True, alpha=0.3)

        # Plot 2: Zone fractions
        zone_stats = zone_result.get("zone_stats", {})
        core_fraction = zone_stats.get("core", {}).get("volume_fraction", 0)
        tail_fraction = zone_stats.get("tail", {}).get("volume_fraction", 0)
        transition_fraction = zone_stats.get("transition", {}).get("volume_fraction", 0)

        fractions = [core_fraction, transition_fraction, tail_fraction]
        ax2.pie(fractions, labels=zones, colors=colors, autopct="%1.1f%%")
        ax2.set_title("Zone Volume Fractions")

        # Plot 3: Zone amplitudes
        core_amplitude = zone_stats.get("core", {}).get("mean_amplitude", 0)
        tail_amplitude = zone_stats.get("tail", {}).get("mean_amplitude", 0)
        transition_amplitude = zone_stats.get("transition", {}).get("mean_amplitude", 0)

        amplitudes = [core_amplitude, transition_amplitude, tail_amplitude]
        ax3.bar(zones, amplitudes, color=colors, alpha=0.7)
        ax3.set_ylabel("Mean Amplitude")
        ax3.set_title("Zone Amplitudes")
        ax3.grid(True, alpha=0.3)

        # Plot 4: Quality metrics
        quality_metrics = zone_result.get("quality_metrics", {})
        overall_score = quality_metrics.get("overall_score", 0)
        amplitude_ordering = quality_metrics.get("amplitude_ordering", False)
        zone_balance = quality_metrics.get("zone_balance", False)

        metrics = ["Overall Score", "Amplitude Ordering", "Zone Balance"]
        values = [overall_score, amplitude_ordering, zone_balance]

        ax4.bar(metrics, values, color=["green", "blue", "orange"], alpha=0.7)
        ax4.set_ylabel("Value")
        ax4.set_title("Quality Metrics")
        ax4.set_ylim(0, 1)
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

