"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for Level B visualization.
"""

from typing import Dict, Any, List
from pathlib import Path

import numpy as np

from .visualization_base import LevelBVisualizerBase
from .visualization_power_law import LevelBVisualizerPowerLaw
from .visualization_node import LevelBVisualizerNode
from .visualization_topological import LevelBVisualizerTopological
from .visualization_zone import LevelBVisualizerZone
from .visualization_dashboard import LevelBVisualizerDashboard
from .visualization_3d import LevelBVisualizer3D


class LevelBVisualizer(LevelBVisualizerBase):
    """
    Visualization tools for Level B analysis results.

    Physical Meaning:
        Creates comprehensive visualizations of Level B analysis results,
        helping to understand the fundamental properties of the phase field
        including power law behavior, zone structure, and topological characteristics.

    Mathematical Foundation:
        Visualizations are based on the theoretical predictions of the
        Riesz operator L_β = μ(-Δ)^β + λ and its spectral properties.
    """

    def __init__(self, style: str = "seaborn-v0_8"):
        """Initialize Level B visualizer."""
        super().__init__(style)
        self._power_law = LevelBVisualizerPowerLaw()
        self._node = LevelBVisualizerNode()
        self._topological = LevelBVisualizerTopological()
        self._zone = LevelBVisualizerZone()
        self._dashboard = LevelBVisualizerDashboard()
        self._visualization_3d = LevelBVisualizer3D()

    def create_comprehensive_report(
        self, results: Dict[str, Any], output_dir: str = "level_b_analysis"
    ) -> None:
        """
        Create comprehensive visualization report.

        Physical Meaning:
            Generates a complete set of visualizations for all Level B
            analysis results, providing a comprehensive view of the
            fundamental properties of the phase field.

        Args:
            results (Dict[str, Any]): All Level B analysis results
            output_dir (str): Directory to save visualizations
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Create individual visualizations
        if "test_B1_power_law_tail" in results:
            self._power_law.visualize_power_law_analysis(
                results["test_B1_power_law_tail"],
                output_path / "power_law_analysis.png",
            )

        if "test_B2_no_spherical_nodes" in results:
            self._node.visualize_node_analysis(
                results["test_B2_no_spherical_nodes"], output_path / "node_analysis.png"
            )

        if "test_B3_topological_charge" in results:
            self._topological.visualize_topological_analysis(
                results["test_B3_topological_charge"],
                output_path / "topological_analysis.png",
            )

        if "test_B4_zone_separation" in results:
            self._zone.visualize_zone_analysis(
                results["test_B4_zone_separation"], output_path / "zone_analysis.png"
            )

        # Create summary dashboard
        self._dashboard.create_summary_dashboard(results, output_path / "summary_dashboard.png")

        print(f"Visualizations saved to {output_path}")

    def create_3d_visualization(
        self,
        field: np.ndarray,
        center: List[float],
        output_path: str = "3d_field_visualization.png",
    ) -> None:
        """
        Create 3D visualization of the field.

        Physical Meaning:
            Creates 3D visualization of the phase field showing
            the spatial structure and amplitude distribution.

        Args:
            field (np.ndarray): 3D field array
            center (List[float]): Center coordinates
            output_path (str): Path to save the plot
        """
        self._visualization_3d.create_3d_visualization(field, center, output_path)

