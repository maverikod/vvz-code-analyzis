"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Node analysis visualization for Level B.
"""

import matplotlib.pyplot as plt
from typing import Dict, Any
from pathlib import Path


class LevelBVisualizerNode:
    """
    Node analysis visualization for Level B.

    Physical Meaning:
        Creates visualizations for node analysis results,
        showing radial profiles, derivatives, and quality metrics.
    """

    def visualize_node_analysis(
        self, result: Dict[str, Any], output_path: Path
    ) -> None:
        """Visualize node analysis results."""
        if not result.get("passed", False):
            return

        analysis_result = result.get("analysis_result", {})
        if not analysis_result:
            return

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

        # Plot 1: Radial profile
        radial_profile = analysis_result.get("radial_profile", {})
        if radial_profile:
            ax1.plot(
                radial_profile["r"],
                radial_profile["A"],
                "b-",
                linewidth=2,
                label="Radial Profile",
            )
            ax1.set_xlabel("Radius r")
            ax1.set_ylabel("Amplitude A(r)")
            ax1.set_title("Radial Profile")
            ax1.grid(True, alpha=0.3)
            ax1.legend()

        # Plot 2: Radial derivative
        radial_derivative = analysis_result.get("radial_derivative", [])
        if len(radial_derivative) > 0 and radial_profile:
            ax2.plot(
                radial_profile["r"], radial_derivative, "r-", linewidth=2, label="dA/dr"
            )
            ax2.axhline(y=0, color="k", linestyle="--", alpha=0.5)
            ax2.set_xlabel("Radius r")
            ax2.set_ylabel("dA/dr")
            ax2.set_title("Radial Derivative")
            ax2.grid(True, alpha=0.3)
            ax2.legend()

        # Plot 3: Sign changes analysis
        sign_changes = analysis_result.get("sign_changes", 0)
        zeros = analysis_result.get("zeros", [])

        ax3.bar(
            ["Sign Changes", "Zeros Found"],
            [sign_changes, len(zeros)],
            color=["red", "blue"],
            alpha=0.7,
        )
        ax3.set_ylabel("Count")
        ax3.set_title("Node Analysis")
        ax3.grid(True, alpha=0.3)

        # Plot 4: Quality assessment
        is_monotonic = analysis_result.get("is_monotonic", False)
        periodic_zeros = analysis_result.get("periodic_zeros", False)

        quality_metrics = ["Monotonic", "No Periodic Zeros", "Low Sign Changes"]
        quality_values = [is_monotonic, not periodic_zeros, sign_changes <= 1]

        colors = ["green" if v else "red" for v in quality_values]
        ax4.bar(quality_metrics, quality_values, color=colors, alpha=0.7)
        ax4.set_ylabel("Pass/Fail")
        ax4.set_title("Quality Assessment")
        ax4.set_ylim(0, 1)
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

