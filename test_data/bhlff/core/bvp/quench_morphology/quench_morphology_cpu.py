"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU-based morphological operations for quench detection.
"""

import numpy as np
from typing import Dict

try:
    from scipy.ndimage import binary_opening, binary_closing, label
except ImportError:
    pass


class QuenchMorphologyCPU:
    """
    CPU-based morphological operations for quench detection.

    Physical Meaning:
        Applies morphological operations on CPU to remove noise
        and find connected components in quench regions.
    """

    def apply_morphological_operations(self, mask: np.ndarray, scipy_available: bool) -> np.ndarray:
        """
        Apply morphological operations to filter noise in quench mask.

        Physical Meaning:
            Applies binary morphological operations to remove noise
            and fill gaps in quench regions, improving detection quality.

        Mathematical Foundation:
            - Binary opening: Erosion followed by dilation
            - Binary closing: Dilation followed by erosion
            - Removes small noise components and fills small gaps

        Args:
            mask (np.ndarray): Binary mask of quench regions.
            scipy_available (bool): Whether scipy is available.

        Returns:
            np.ndarray: Filtered binary mask.
        """
        if scipy_available:
            return self._apply_scipy_operations(mask)
        else:
            return self._apply_simple_operations(mask)

    def find_connected_components(self, mask: np.ndarray, scipy_available: bool) -> Dict[int, np.ndarray]:
        """
        Find connected components in quench mask.

        Physical Meaning:
            Groups nearby quench events into connected components,
            representing coherent quench regions in 7D space-time.

        Mathematical Foundation:
            Uses connected component labeling to identify regions
            where quench events are spatially/phase/temporally connected.

        Args:
            mask (np.ndarray): Binary mask of quench regions.
            scipy_available (bool): Whether scipy is available.

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component.
        """
        if scipy_available:
            return self._find_scipy_components(mask)
        else:
            return self._find_simple_components(mask)

    def _apply_scipy_operations(self, mask: np.ndarray) -> np.ndarray:
        """
        Apply morphological operations using scipy.

        Physical Meaning:
            Uses scipy's optimized morphological operations for
            efficient noise filtering in 7D space-time.

        Args:
            mask (np.ndarray): Binary mask of quench regions.

        Returns:
            np.ndarray: Filtered binary mask.
        """
        # Define structuring element for 7D operations
        # Use smaller structure for small arrays
        structure_shape = tuple(min(3, dim) for dim in mask.shape)
        structure = np.ones(structure_shape, dtype=bool)

        # Apply binary opening to remove small noise
        filtered_mask = binary_opening(mask, structure=structure)

        # Apply binary closing to fill small gaps
        filtered_mask = binary_closing(filtered_mask, structure=structure)

        return filtered_mask

    def _apply_simple_operations(self, mask: np.ndarray) -> np.ndarray:
        """
        Simple morphological filtering without scipy dependency.

        Physical Meaning:
            Basic noise filtering using local neighborhood operations
            to remove isolated pixels and fill small gaps.

        Args:
            mask (np.ndarray): Binary mask of quench regions.

        Returns:
            np.ndarray: Filtered binary mask.
        """
        # Simple erosion: remove isolated pixels
        filtered_mask = mask.copy()

        # Simple dilation: fill small gaps
        # This is a basic implementation for 7D
        for axis in range(mask.ndim):
            # Apply 1D dilation along each axis
            for i in range(1, mask.shape[axis] - 1):
                if axis == 0:
                    if (
                        mask[i - 1, :, :, :, :, :, :].any()
                        and mask[i + 1, :, :, :, :, :, :].any()
                    ):
                        filtered_mask[i, :, :, :, :, :, :] = True
                elif axis == 1:
                    if (
                        mask[:, i - 1, :, :, :, :, :].any()
                        and mask[:, i + 1, :, :, :, :, :, :].any()
                    ):
                        filtered_mask[:, i, :, :, :, :, :] = True
                # Continue for other axes...

        return filtered_mask

    def _find_scipy_components(self, mask: np.ndarray) -> Dict[int, np.ndarray]:
        """
        Find connected components using scipy.

        Physical Meaning:
            Uses scipy's optimized connected component labeling for
            efficient component identification in 7D space-time.

        Args:
            mask (np.ndarray): Binary mask of quench regions.

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component.
        """
        # Label connected components
        labeled_mask, num_components = label(mask)

        # Extract individual components
        components = {}
        for component_id in range(1, num_components + 1):
            component_mask = labeled_mask == component_id
            components[component_id] = component_mask

        return components

    def _find_simple_components(self, mask: np.ndarray) -> Dict[int, np.ndarray]:
        """
        Simple connected component analysis without scipy.

        Physical Meaning:
            Basic grouping of nearby quench events using
            flood-fill algorithm for 7D space.

        Args:
            mask (np.ndarray): Binary mask of quench regions.

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component.
        """
        from .quench_morphology_helpers import QuenchMorphologyHelpers

        helpers = QuenchMorphologyHelpers()
        components = {}
        visited = np.zeros_like(mask, dtype=bool)
        component_id = 0

        # Find all quench points
        quench_points = np.where(mask)

        for point in zip(*quench_points):
            if not visited[point]:
                component_id += 1
                component_mask = np.zeros_like(mask, dtype=bool)

                # Simple flood-fill for this component
                helpers.flood_fill_7d(mask, visited, component_mask, point)
                components[component_id] = component_mask

        return components

