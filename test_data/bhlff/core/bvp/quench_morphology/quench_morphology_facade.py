"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for quench morphology operations.
"""

import numpy as np
from typing import Dict, Any

from .quench_morphology_base import QuenchMorphologyBase
from .quench_morphology_cpu import QuenchMorphologyCPU
from .quench_morphology_cuda import QuenchMorphologyCUDA


class QuenchMorphology(QuenchMorphologyBase):
    """
    Morphological operations for quench detection.

    Physical Meaning:
        Applies morphological operations to remove noise and fill gaps
        in quench regions, improving detection quality. Groups nearby
        quench events into connected components representing coherent
        quench structures in 7D space-time.

    Mathematical Foundation:
        - Binary opening: Erosion followed by dilation
        - Binary closing: Dilation followed by erosion
        - Connected component analysis: Groups spatially/phase/temporally connected events
    """

    def __init__(self):
        """Initialize morphological operations processor."""
        super().__init__()
        self._cpu_processor = QuenchMorphologyCPU()
        self._cuda_processor = QuenchMorphologyCUDA()

    def apply_morphological_operations(self, mask: np.ndarray) -> np.ndarray:
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

        Returns:
            np.ndarray: Filtered binary mask.
        """
        return self._cpu_processor.apply_morphological_operations(
            mask, self.scipy_available
        )

    def find_connected_components(self, mask: np.ndarray) -> Dict[int, np.ndarray]:
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

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component.
        """
        return self._cpu_processor.find_connected_components(
            mask, self.scipy_available
        )

    def apply_morphological_operations_cuda(self, mask_gpu):
        """
        Apply morphological operations using CUDA acceleration.

        Physical Meaning:
            Applies binary morphological operations on GPU for
            efficient noise filtering in 7D space-time.

        Args:
            mask_gpu: GPU array of quench regions.

        Returns:
            CuPy array: Filtered binary mask (kept on GPU).
        """
        return self._cuda_processor.apply_morphological_operations_cuda(
            mask_gpu, self.cuda_available, self._cpu_processor
        )

    def find_connected_components_cuda(self, mask_gpu) -> Dict[int, np.ndarray]:
        """
        Find connected components using CUDA acceleration.

        Physical Meaning:
            Groups nearby quench events into connected components
            using GPU acceleration for efficient processing.

        Args:
            mask_gpu: GPU array of quench regions.

        Returns:
            Dict[int, np.ndarray]: Dictionary mapping component IDs to
                binary masks of each component (transferred to CPU).
        """
        return self._cuda_processor.find_connected_components_cuda(
            mask_gpu, self.cuda_available, self._cpu_processor
        )

