"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase coherence computation for phase components.
"""

import numpy as np
from typing import List

from .phase_components_cuda_helpers import PhaseComponentsCUDAHelpers


class PhaseComponentsCoherence:
    """
    Phase coherence computation for phase components.

    Physical Meaning:
        Computes phase coherence measure across the U(1)³ structure,
        indicating the degree of synchronization between components.
    """

    def __init__(self, theta_components: List[np.ndarray], use_cuda: bool):
        """
        Initialize coherence computer.

        Args:
            theta_components (List[np.ndarray]): Phase components.
            use_cuda (bool): Whether to use CUDA.
        """
        self.theta_components = theta_components
        self._cuda_helpers = PhaseComponentsCUDAHelpers(use_cuda)

    def compute_phase_coherence(self) -> np.ndarray:
        """
        Compute phase coherence measure.

        Physical Meaning:
            Computes a measure of phase coherence across the
            U(1)³ structure, indicating the degree of
            synchronization between the three phase components.

        Mathematical Foundation:
            Coherence = |Σ_a exp(iΘ_a)| / 3
            where the magnitude indicates coherence strength.

        Returns:
            np.ndarray: Phase coherence measure.
        """
        # Sum of complex exponentials
        coherence_sum = np.zeros_like(self.theta_components[0])
        coherence_sum = self._cuda_helpers.to_gpu(coherence_sum)

        for theta_a in self.theta_components:
            theta_a_gpu = self._cuda_helpers.to_gpu(theta_a)
            coherence_sum += self._cuda_helpers.cuda_exp(
                1j * self._cuda_helpers.cuda_angle(theta_a_gpu)
            )

        # Normalize by number of components
        coherence = self._cuda_helpers.cuda_abs(coherence_sum) / 3.0

        return self._cuda_helpers.to_cpu(coherence)

