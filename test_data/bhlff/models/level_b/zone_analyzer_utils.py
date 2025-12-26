"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Utility functions for Level B zone analysis visualization and parameter sweeps.

This module contains helper routines that support `LevelBZoneAnalyzer` by
providing
- high-quality visualization of zone separation results, and
- batch execution across ranges of threshold parameters.

Theoretical Background:
    Zone separation decomposes the field into core, transition, and tail regions
    using local indicators N, S, and C with threshold criteria. Visualization
    and parameter sensitivity studies are auxiliary tasks that do not belong in
    the analyzer's core logic and are factored out here to keep files small and
    maintainable.

Example:
    >>> from bhlff.models.level_b.zone_analyzer_utils import (
    ...     visualize_zone_analysis, run_zone_analysis_variations,
    ... )
    >>> analysis = analyzer.separate_zones(field, center, thresholds)
    >>> visualize_zone_analysis(analysis, output_path="zone.png")
"""

# flake8: noqa: E501

from typing import Dict, Any, List
import numpy as np
import matplotlib.pyplot as plt


def visualize_zone_analysis(analysis_result: Dict[str, Any], output_path: str) -> None:
    """
    Render a 2x2 figure showing zone masks and indicators.

    Args:
        analysis_result (Dict[str, Any]): Output of analyzer.separate_zones
        output_path (str): Path to save the figure
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Plot 1: Core zone map (2D slice)
    ax1 = axes[0, 0]
    core_slice = analysis_result["core_mask"][
        :, :, analysis_result["core_mask"].shape[2] // 2
    ]
    im1 = ax1.imshow(core_slice, cmap="viridis", origin="lower")
    ax1.set_title("Core Zone Map")
    ax1.set_xlabel("x")
    ax1.set_ylabel("y")
    plt.colorbar(im1, ax=ax1)

    # Plot 2: Tail zone map (2D slice)
    ax2 = axes[0, 1]
    tail_slice = analysis_result["tail_mask"][
        :, :, analysis_result["tail_mask"].shape[2] // 2
    ]
    im2 = ax2.imshow(tail_slice, cmap="plasma", origin="lower")
    ax2.set_title("Tail Zone Map")
    ax2.set_xlabel("x")
    ax2.set_ylabel("y")
    plt.colorbar(im2, ax=ax2)

    # Plot 3: N indicator (2D slice)
    ax3 = axes[1, 0]
    N_slice = analysis_result["indicators"]["N"][
        :, :, analysis_result["indicators"]["N"].shape[2] // 2
    ]
    im3 = ax3.imshow(N_slice, cmap="hot", origin="lower")
    ax3.set_title("N Indicator (Norm Gradient)")
    ax3.set_xlabel("x")
    ax3.set_ylabel("y")
    plt.colorbar(im3, ax=ax3)

    # Plot 4: S indicator (2D slice)
    ax4 = axes[1, 1]
    S_slice = analysis_result["indicators"]["S"][
        :, :, analysis_result["indicators"]["S"].shape[2] // 2
    ]
    im4 = ax4.imshow(S_slice, cmap="cool", origin="lower")
    ax4.set_title("S Indicator (Second Derivative)")
    ax4.set_xlabel("x")
    ax4.set_ylabel("y")
    plt.colorbar(im4, ax=ax4)

    # Text summary
    zone_stats = analysis_result["zone_stats"]
    quality = analysis_result["quality_metrics"]
    textstr = (
        f'Core Radius: {analysis_result["r_core"]:.2f}\n'
        f'Tail Radius: {analysis_result["r_tail"]:.2f}\n'
        f'Core Fraction: {zone_stats["core"]["volume_fraction"]:.3f}\n'
        f'Tail Fraction: {zone_stats["tail"]["volume_fraction"]:.3f}\n'
        f'Quality Score: {quality["overall_score"]:.3f}'
    )
    ax4.text(
        0.05,
        0.95,
        textstr,
        transform=ax4.transAxes,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def run_zone_analysis_variations(
    separate_fn,
    field: np.ndarray,
    center: List[float],
    threshold_ranges: Dict[str, List[float]],
) -> Dict[str, Any]:
    """
    Execute zone analysis across threshold grids.

    Args:
        separate_fn: Callable compatible with analyzer.separate_zones
        field (np.ndarray): Input field
        center (List[float]): Defect center [x, y, z]
        threshold_ranges (Dict[str, List[float]]): Ranges for N_core, S_core, N_tail, S_tail

    Returns:
        Dict[str, Any]: Mapping of parameter keys to analysis results or errors
    """
    results: Dict[str, Any] = {}
    for N_core in threshold_ranges.get("N_core", [3.0]):
        for S_core in threshold_ranges.get("S_core", [1.0]):
            for N_tail in threshold_ranges.get("N_tail", [0.3]):
                for S_tail in threshold_ranges.get("S_tail", [0.3]):
                    thresholds = {
                        "N_core": N_core,
                        "S_core": S_core,
                        "N_tail": N_tail,
                        "S_tail": S_tail,
                    }
                    key = f"Nc{N_core}_Sc{S_core}_Nt{N_tail}_St{S_tail}"
                    try:
                        results[key] = separate_fn(field, center, thresholds)
                    except Exception as e:  # noqa: BLE001
                        results[key] = {"error": str(e), "passed": False}
    return results
