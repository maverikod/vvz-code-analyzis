"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological analysis visualization for Level B.
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any
from pathlib import Path


class LevelBVisualizerTopological:
    """
    Topological analysis visualization for Level B.

    Physical Meaning:
        Creates visualizations for topological charge analysis results,
        showing charge values, errors, and integration contours.
    """

    def visualize_topological_analysis(
        self, result: Dict[str, Any], output_path: Path
    ) -> None:
        """Visualize topological charge analysis results."""
        if not result.get("passed", False):
            return

        charge_result = result.get("charge_result", {})
        if not charge_result:
            return

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

        # Plot 1: Charge value
        charge = charge_result.get("charge", 0)
        integer_charge = charge_result.get("integer_charge", 0)
        error = charge_result.get("error", 0)

        ax1.bar(
            ["Measured", "Integer"],
            [charge, integer_charge],
            color=["blue", "red"],
            alpha=0.7,
        )
        ax1.set_ylabel("Charge Value")
        ax1.set_title(f"Topological Charge (Error: {error:.3f})")
        ax1.grid(True, alpha=0.3)

        # Plot 2: Error analysis
        ax2.bar(["Error"], [error], color="orange", alpha=0.7)
        ax2.axhline(y=0.01, color="red", linestyle="--", label="Threshold (1%)")
        ax2.set_ylabel("Error")
        ax2.set_title("Charge Error Analysis")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Contour visualization
        contour_points = charge_result.get("contour_points", [])
        if contour_points:
            contour_array = np.array(contour_points)
            ax3.scatter(
                contour_array[:, 0],
                contour_array[:, 1],
                c=range(len(contour_array)),
                cmap="viridis",
                s=50,
            )
            ax3.set_xlabel("x")
            ax3.set_ylabel("y")
            ax3.set_title("Integration Contour")
            ax3.grid(True, alpha=0.3)

        # Plot 4: Quality metrics
        integration_radius = charge_result.get("integration_radius", 0)
        contour_count = len(contour_points)

        metrics = ["Integration Radius", "Contour Points", "Error < 1%"]
        values = [integration_radius, contour_count, error < 0.01]

        ax4.bar(metrics, values, color=["blue", "green", "red"], alpha=0.7)
        ax4.set_ylabel("Value")
        ax4.set_title("Quality Metrics")
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

