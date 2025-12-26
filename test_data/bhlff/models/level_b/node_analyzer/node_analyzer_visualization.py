"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Visualization methods for node analyzer.

This module provides visualization methods as a mixin class.
"""

import matplotlib.pyplot as plt
from typing import Dict, Any


class LevelBNodeAnalyzerVisualizationMixin:
    """Mixin providing visualization methods."""
    
    def visualize_node_analysis(
        self, analysis_result: Dict[str, Any], output_path: str = "node_analysis.png"
    ) -> None:
        """
        Visualize node analysis results.
        
        Physical Meaning:
            Creates visualization of the node analysis showing
            radial profile, derivative, and node detection results.
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Plot 1: Radial profile
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
        
        # Plot 2: Radial derivative
        ax2.plot(
            radial_profile["r"],
            analysis_result["radial_derivative"],
            "r-",
            linewidth=2,
            label="dA/dr",
        )
        ax2.axhline(y=0, color="k", linestyle="--", alpha=0.5)
        ax2.set_xlabel("Radius r")
        ax2.set_ylabel("dA/dr")
        ax2.set_title("Radial Derivative")
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        # Add text with results
        textstr = f'Sign Changes: {analysis_result["sign_changes"]}\n'
        textstr += f'Zeros: {len(analysis_result["zeros"])}\n'
        textstr += f'Periodic: {analysis_result["periodic_zeros"]}\n'
        textstr += f'Monotonic: {analysis_result["is_monotonic"]}\n'
        textstr += f'Passed: {analysis_result["passed"]}'
        
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

