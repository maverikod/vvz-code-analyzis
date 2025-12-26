"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for quench morphology operations.
"""

import numpy as np
from typing import Tuple


class QuenchMorphologyHelpers:
    """
    Helper methods for quench morphology operations.

    Physical Meaning:
        Provides helper methods for flood-fill algorithms and
        other utility functions used in morphological operations.
    """

    def flood_fill_7d(
        self,
        mask: np.ndarray,
        visited: np.ndarray,
        component_mask: np.ndarray,
        start_point: Tuple[int, ...],
    ) -> None:
        """
        Flood-fill algorithm for 7D connected components.

        Physical Meaning:
            Recursively fills connected quench regions starting from
            a seed point, identifying coherent quench structures.

        Args:
            mask (np.ndarray): Binary mask of quench regions.
            visited (np.ndarray): Visited points mask.
            component_mask (np.ndarray): Current component mask.
            start_point (Tuple[int, ...]): Starting point for flood-fill.
        """
        stack = [start_point]

        while stack:
            point = stack.pop()

            if visited[point]:
                continue

            visited[point] = True
            component_mask[point] = True

            # Check 7D neighbors (3^7 = 2187 neighbors, but we check only immediate ones)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for dz in [-1, 0, 1]:
                        for dphi1 in [-1, 0, 1]:
                            for dphi2 in [-1, 0, 1]:
                                for dphi3 in [-1, 0, 1]:
                                    for dt in [-1, 0, 1]:
                                        if (
                                            dx
                                            == dy
                                            == dz
                                            == dphi1
                                            == dphi2
                                            == dphi3
                                            == dt
                                            == 0
                                        ):
                                            continue

                                        neighbor = (
                                            point[0] + dx,
                                            point[1] + dy,
                                            point[2] + dz,
                                            point[3] + dphi1,
                                            point[4] + dphi2,
                                            point[5] + dphi3,
                                            point[6] + dt,
                                        )

                                        # Check bounds
                                        if (
                                            0 <= neighbor[0] < mask.shape[0]
                                            and 0 <= neighbor[1] < mask.shape[1]
                                            and 0 <= neighbor[2] < mask.shape[2]
                                            and 0 <= neighbor[3] < mask.shape[3]
                                            and 0 <= neighbor[4] < mask.shape[4]
                                            and 0 <= neighbor[5] < mask.shape[5]
                                            and 0 <= neighbor[6] < mask.shape[6]
                                        ):

                                            if mask[neighbor] and not visited[neighbor]:
                                                stack.append(neighbor)

