"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

3D visualization for Level B.
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import List


class LevelBVisualizer3D:
    """
    3D visualization for Level B.

    Physical Meaning:
        Creates 3D visualizations of the phase field showing
        the spatial structure and amplitude distribution.
    """

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
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection="3d")

        # Create coordinate grids
        x = np.arange(field.shape[0])
        y = np.arange(field.shape[1])
        z = np.arange(field.shape[2])
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Get field amplitude
        amplitude = np.abs(field)

        # Create 3D scatter plot
        scatter = ax.scatter(
            X.flatten(),
            Y.flatten(),
            Z.flatten(),
            c=amplitude.flatten(),
            cmap="viridis",
            alpha=0.6,
        )

        # Mark the center
        ax.scatter(
            center[0], center[1], center[2], c="red", s=100, marker="*", label="Center"
        )

        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
        ax.set_title("3D Field Visualization")

        plt.colorbar(scatter, label="Amplitude")
        plt.legend()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

