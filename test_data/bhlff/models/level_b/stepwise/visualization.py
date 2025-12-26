"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Visualization methods for stepwise power law analysis.

This module implements visualization methods for displaying power law
analysis results, including radial profiles and log-log fits.

Example:
    >>> visualizer = StepwiseVisualizer()
    >>> visualizer.visualize_power_law_analysis(result, output_path)
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, Tuple


class StepwiseVisualizer:
    """
    Visualization for stepwise power law analysis.

    Physical Meaning:
        Creates visualizations of power law analysis showing radial profiles,
        log-log fits, and quality metrics for validation and interpretation.
    """

    def __init__(
        self,
        figure_size: Tuple[int, int] = (10, 8),
        line_color: str = "#1f77b4",
        stepwise_color: str = "#d62728",
    ):
        """
        Initialize visualizer.

        Physical Meaning:
            Sets up visualizer with default styling parameters for
            creating publication-quality plots of analysis results.

        Args:
            figure_size (Tuple[int, int]): Figure size (width, height).
            line_color (str): Color for main lines.
            stepwise_color (str): Color for stepwise structure elements.
        """
        self.figure_size = figure_size
        self.line_color = line_color
        self.stepwise_color = stepwise_color

    def visualize_power_law_analysis(
        self,
        analysis_result: Dict[str, Any],
        output_path: str = "power_law_analysis.png",
    ) -> None:
        """
        Visualize power law analysis results.

        Physical Meaning:
            Creates visualization of the power law analysis showing
            the radial profile, log-log fit, and quality metrics.

        Args:
            analysis_result (Dict[str, Any]): Results from analyze_power_law_tail.
            output_path (str): Path to save the plot.
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        radial_profile = analysis_result["radial_profile"]
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

        tail_data = analysis_result["tail_data"]
        ax2.scatter(
            tail_data["log_r"], tail_data["log_A"], alpha=0.6, s=20, label="Data"
        )

        if len(tail_data["log_r"]) > 1:
            slope = analysis_result["slope"]
            intercept = analysis_result.get("intercept", 0)
            log_r_fit = np.linspace(
                tail_data["log_r"].min(), tail_data["log_r"].max(), 100
            )
            log_A_fit = slope * log_r_fit + intercept
            ax2.plot(
                log_r_fit,
                log_A_fit,
                "r-",
                linewidth=2,
                label=f"Fit: slope={slope:.3f}",
            )

        ax2.set_xlabel("log(r)")
        ax2.set_ylabel("log(A)")
        ax2.set_title(f'Power Law Fit (R²={analysis_result["r_squared"]:.3f})')
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        textstr = f'Slope: {analysis_result["slope"]:.3f}\n'
        textstr += f'Theoretical: {analysis_result["theoretical_slope"]:.3f}\n'
        textstr += f'Error: {analysis_result["relative_error"]:.1%}\n'
        textstr += f'R²: {analysis_result["r_squared"]:.3f}'

        ax2.text(
            0.05,
            0.95,
            textstr,
            transform=ax2.transAxes,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        )

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
