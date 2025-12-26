"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase analysis for BVP framework.

This module implements comprehensive phase analysis including
phase coherence, gradient analysis, and topological characterization.
"""

import numpy as np
from typing import Dict, Any, Tuple, List, Optional

from ...domain import Domain
from ..bvp_constants import BVPConstants


class PhaseAnalysis:
    """
    Analyzes phase structure of BVP fields.

    Physical Meaning:
        Analyzes the phase structure of BVP fields to understand
        topological characteristics and phase coherence.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any], constants: BVPConstants):
        """
        Initialize phase analysis.

        Physical Meaning:
            Sets up phase analysis with domain information and
            configuration parameters for comprehensive phase analysis.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Configuration parameters.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants

        # Analysis parameters
        self.coherence_threshold = config.get("coherence_threshold", 0.5)
        self.gradient_threshold = config.get("gradient_threshold", 1.0)

    def analyze_phase_structure(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Analyze phase structure of the field.

        Physical Meaning:
            Analyzes the phase structure of the BVP field to understand
            the topological characteristics and phase coherence.

        Args:
            field (np.ndarray): BVP field for analysis.

        Returns:
            Dict[str, Any]: Phase structure analysis.
        """
        # Convert to complex field for phase analysis
        if np.iscomplexobj(field):
            complex_field = field
        else:
            complex_field = field.astype(complex)

        # Compute phase field
        phase = np.angle(complex_field)
        amplitude = np.abs(complex_field)

        # Compute phase gradients
        gradients = self._compute_phase_gradients(phase)

        # Analyze phase coherence
        coherence_analysis = self._analyze_phase_coherence(phase)

        # Analyze phase gradients
        gradient_analysis = self._analyze_phase_gradients(gradients)

        # Analyze phase variance
        variance_analysis = self._analyze_phase_variance(phase)

        return {
            "phase_coherence": coherence_analysis["coherence"],
            "phase_variance": variance_analysis["variance"],
            "gradient_mean": gradient_analysis["mean"],
            "gradient_std": gradient_analysis["std"],
            "gradient_max": gradient_analysis["max"],
            "high_gradient_fraction": gradient_analysis["high_fraction"],
            "coherence_regions": coherence_analysis["regions"],
            "gradient_regions": gradient_analysis["regions"],
        }

    def _compute_phase_gradients(self, phase: np.ndarray) -> List[np.ndarray]:
        """Compute phase gradients along all dimensions."""
        gradients = []
        for i in range(phase.ndim):
            grad = np.gradient(phase, axis=i)
            gradients.append(grad)
        return gradients

    def _analyze_phase_coherence(self, phase: np.ndarray) -> Dict[str, Any]:
        """Analyze phase coherence of the field."""
        # Compute local phase coherence
        coherence_field = self._compute_local_coherence(phase)

        # Compute global coherence
        global_coherence = np.mean(coherence_field)

        # Find coherent regions
        coherent_regions = coherence_field > self.coherence_threshold
        coherent_fraction = np.sum(coherent_regions) / coherent_regions.size

        # Analyze coherence distribution
        coherence_std = np.std(coherence_field)
        coherence_max = np.max(coherence_field)
        coherence_min = np.min(coherence_field)

        return {
            "coherence": float(global_coherence),
            "coherence_std": float(coherence_std),
            "coherence_max": float(coherence_max),
            "coherence_min": float(coherence_min),
            "coherent_fraction": float(coherent_fraction),
            "regions": coherent_regions,
        }

    def _compute_local_coherence(self, phase: np.ndarray) -> np.ndarray:
        """Compute local phase coherence."""
        # Compute local phase coherence using windowed analysis
        window_size = 3  # Small window for local analysis

        coherence_field = np.zeros_like(phase)

        # Apply windowed coherence computation
        for i in range(phase.shape[0]):
            for j in range(phase.shape[1]) if phase.ndim > 1 else [0]:
                # Define window bounds
                i_start = max(0, i - window_size // 2)
                i_end = min(phase.shape[0], i + window_size // 2 + 1)

                if phase.ndim > 1:
                    j_start = max(0, j - window_size // 2)
                    j_end = min(phase.shape[1], j + window_size // 2 + 1)

                    # Extract window
                    window = phase[i_start:i_end, j_start:j_end]
                else:
                    window = phase[i_start:i_end]

                # Compute coherence in window
                if window.size > 1:
                    # Compute phase differences
                    phase_diff = np.diff(window.flatten())

                    # Handle phase wrapping
                    phase_diff = np.where(
                        phase_diff > np.pi, phase_diff - 2 * np.pi, phase_diff
                    )
                    phase_diff = np.where(
                        phase_diff < -np.pi, phase_diff + 2 * np.pi, phase_diff
                    )

                    # Compute coherence as inverse of phase variance
                    coherence = 1.0 / (1.0 + np.var(phase_diff))
                else:
                    coherence = 1.0

                coherence_field[i, j] = coherence

        return coherence_field

    def _analyze_phase_gradients(self, gradients: List[np.ndarray]) -> Dict[str, Any]:
        """Analyze phase gradient statistics."""
        # Compute gradient magnitude
        grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients))

        # Compute gradient statistics
        grad_mean = np.mean(grad_magnitude)
        grad_std = np.std(grad_magnitude)
        grad_max = np.max(grad_magnitude)
        grad_min = np.min(grad_magnitude)

        # Find regions of high gradient
        high_grad_threshold = grad_mean + 2 * grad_std
        high_grad_regions = grad_magnitude > high_grad_threshold
        high_grad_fraction = np.sum(high_grad_regions) / high_grad_regions.size

        # Analyze gradient distribution
        grad_skewness = self._compute_skewness(grad_magnitude)
        grad_kurtosis = self._compute_kurtosis(grad_magnitude)

        return {
            "mean": float(grad_mean),
            "std": float(grad_std),
            "max": float(grad_max),
            "min": float(grad_min),
            "high_fraction": float(high_grad_fraction),
            "skewness": float(grad_skewness),
            "kurtosis": float(grad_kurtosis),
            "regions": high_grad_regions,
        }

    def _analyze_phase_variance(self, phase: np.ndarray) -> Dict[str, Any]:
        """Analyze phase variance and distribution."""
        # Compute phase variance
        phase_variance = np.var(phase)
        phase_std = np.std(phase)

        # Compute phase range
        phase_min = np.min(phase)
        phase_max = np.max(phase)
        phase_range = phase_max - phase_min

        # Analyze phase distribution
        phase_skewness = self._compute_skewness(phase)
        phase_kurtosis = self._compute_kurtosis(phase)

        # Compute phase uniformity
        phase_uniformity = 1.0 / (1.0 + phase_variance)

        return {
            "variance": float(phase_variance),
            "std": float(phase_std),
            "min": float(phase_min),
            "max": float(phase_max),
            "range": float(phase_range),
            "skewness": float(phase_skewness),
            "kurtosis": float(phase_kurtosis),
            "uniformity": float(phase_uniformity),
        }

    def _compute_skewness(self, data: np.ndarray) -> float:
        """Compute skewness of data distribution."""
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 3))

    def _compute_kurtosis(self, data: np.ndarray) -> float:
        """Compute kurtosis of data distribution."""
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 4)) - 3.0

    def analyze_phase_transitions(self, phase: np.ndarray) -> Dict[str, Any]:
        """
        Analyze phase transitions in the field.

        Physical Meaning:
            Identifies and analyzes phase transitions in the field
            to understand topological changes and defect formation.

        Args:
            phase (np.ndarray): Phase field data.

        Returns:
            Dict[str, Any]: Phase transition analysis.
        """
        # Compute phase differences
        phase_diff = np.diff(phase, axis=0)

        # Handle phase wrapping
        phase_diff = np.where(phase_diff > np.pi, phase_diff - 2 * np.pi, phase_diff)
        phase_diff = np.where(phase_diff < -np.pi, phase_diff + 2 * np.pi, phase_diff)

        # Find significant transitions
        transition_threshold = np.std(phase_diff) * 2
        significant_transitions = np.abs(phase_diff) > transition_threshold

        # Analyze transition statistics
        transition_count = np.sum(significant_transitions)
        transition_fraction = transition_count / significant_transitions.size

        # Compute transition strength
        transition_strength = (
            np.mean(np.abs(phase_diff[significant_transitions]))
            if transition_count > 0
            else 0.0
        )

        return {
            "transition_count": int(transition_count),
            "transition_fraction": float(transition_fraction),
            "transition_strength": float(transition_strength),
            "transition_threshold": float(transition_threshold),
            "transitions": significant_transitions,
        }
