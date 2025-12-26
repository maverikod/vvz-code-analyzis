"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law visualization for Level B.
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any
from pathlib import Path


class LevelBVisualizerPowerLaw:
    """
    Power law visualization for Level B.

    Physical Meaning:
        Creates visualizations for power law analysis results,
        showing radial profiles, log-log fits, and quality metrics.
    """

    def visualize_power_law_analysis(
        self, result: Dict[str, Any], output_path: Path
    ) -> None:
        """Visualize power law analysis results."""
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

        # Plot 2: Log-log fit
        tail_data = analysis_result.get("tail_data", {})
        if tail_data and "log_r" in tail_data and "log_A" in tail_data:
            ax2.scatter(
                tail_data["log_r"], tail_data["log_A"], alpha=0.6, s=20, label="Data"
            )

            # Plot fitted line
            if len(tail_data["log_r"]) > 1:
                slope = analysis_result.get("slope", 0)
                log_r_fit = np.linspace(
                    tail_data["log_r"].min(), tail_data["log_r"].max(), 100
                )
                log_A_fit = slope * log_r_fit
                ax2.plot(
                    log_r_fit,
                    log_A_fit,
                    "r-",
                    linewidth=2,
                    label=f"Fit: slope={slope:.3f}",
                )

            ax2.set_xlabel("log(r)")
            ax2.set_ylabel("log(A)")
            ax2.set_title(
                f'Power Law Fit (R²={analysis_result.get("r_squared", 0):.3f})'
            )
            ax2.grid(True, alpha=0.3)
            ax2.legend()

        # Plot 3: Error analysis
        theoretical_slope = analysis_result.get("theoretical_slope", 0)
        slope = analysis_result.get("slope", 0)
        relative_error = analysis_result.get("relative_error", 0)

        ax3.bar(
            ["Theoretical", "Measured"],
            [theoretical_slope, slope],
            color=["blue", "red"],
            alpha=0.7,
        )
        ax3.set_ylabel("Slope")
        ax3.set_title(f"Slope Comparison (Error: {relative_error:.1%})")
        ax3.grid(True, alpha=0.3)

        # Plot 4: Quality metrics
        metrics = ["R²", "Log Range", "Error"]
        values = [
            analysis_result.get("r_squared", 0),
            analysis_result.get("log_range", 0),
            1 - analysis_result.get("relative_error", 1),
        ]

        ax4.bar(metrics, values, color=["green", "orange", "purple"], alpha=0.7)
        ax4.set_ylabel("Value")
        ax4.set_title("Quality Metrics")
        ax4.set_ylim(0, 1)
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

