"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating pattern detection utilities for Level C.

This module implements pattern detection functions for beating
analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore


class BeatingPatternDetector:
    """
    Pattern detection utilities for beating analysis.

    Physical Meaning:
        Provides pattern detection functions for beating analysis,
        including temporal, spatial, and phase pattern detection.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating pattern detector.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def calculate_pattern_detection(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate pattern detection in the envelope field.

        Physical Meaning:
            Detects patterns in the envelope field that may
            indicate beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Pattern detection results.
        """
        self.logger.info("Calculating pattern detection")

        # Detect temporal patterns
        temporal_patterns = self._detect_temporal_patterns(envelope)

        # Detect spatial patterns
        spatial_patterns = self._detect_spatial_patterns(envelope)

        # Detect phase patterns
        phase_patterns = self._detect_phase_patterns(envelope)

        # Calculate pattern statistics
        pattern_stats = self._calculate_pattern_statistics(
            temporal_patterns, spatial_patterns, phase_patterns
        )

        results = {
            "temporal_patterns": temporal_patterns,
            "spatial_patterns": spatial_patterns,
            "phase_patterns": phase_patterns,
            "pattern_stats": pattern_stats,
        }

        self.logger.info("Pattern detection completed")
        return results

    def _detect_temporal_patterns(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect temporal patterns in the envelope field.

        Physical Meaning:
            Detects temporal patterns that may indicate
            beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            List[Dict[str, Any]]: List of detected temporal patterns.
        """
        patterns = []

        # Analyze temporal patterns
        if envelope.ndim > 1:
            temporal_data = envelope.reshape(-1, envelope.shape[-1])

            for i in range(temporal_data.shape[0]):
                data = temporal_data[i]

                # Detect patterns in this temporal slice
                pattern = self._detect_pattern_in_data(data)
                if pattern:
                    patterns.append(
                        {"type": "temporal", "index": i, "pattern": pattern}
                    )

        return patterns

    def _detect_spatial_patterns(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect spatial patterns in the envelope field.

        Physical Meaning:
            Detects spatial patterns that may indicate
            beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            List[Dict[str, Any]]: List of detected spatial patterns.
        """
        patterns = []

        # Analyze spatial patterns
        if envelope.ndim > 1:
            spatial_data = envelope.reshape(envelope.shape[0], -1)

            for i in range(spatial_data.shape[1]):
                data = spatial_data[:, i]

                # Detect patterns in this spatial slice
                pattern = self._detect_pattern_in_data(data)
                if pattern:
                    patterns.append({"type": "spatial", "index": i, "pattern": pattern})

        return patterns

    def _detect_phase_patterns(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect phase patterns in the envelope field.

        Physical Meaning:
            Detects phase patterns that may indicate
            beating phenomena.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            List[Dict[str, Any]]: List of detected phase patterns.
        """
        patterns = []

        # Analyze phase patterns
        if envelope.ndim > 1:
            phase_indices = [3, 4, 5]  # Phase dimensions
            phase_data = envelope.take(phase_indices, axis=0)

            for i in range(phase_data.shape[0]):
                data = phase_data[i].flatten()

                # Detect patterns in this phase slice
                pattern = self._detect_pattern_in_data(data)
                if pattern:
                    patterns.append({"type": "phase", "index": i, "pattern": pattern})

        return patterns

    def _detect_pattern_in_data(self, data: np.ndarray) -> Dict[str, Any]:
        """
        Detect patterns in a data array.

        Physical Meaning:
            Detects patterns in the data that may indicate
            beating phenomena.

        Args:
            data (np.ndarray): Input data array.

        Returns:
            Dict[str, Any]: Detected pattern information.
        """
        # Simple pattern detection based on variance
        variance = np.var(data)
        mean = np.mean(data)

        if variance > 0.1 * mean:  # Threshold for pattern detection
            return {
                "variance": variance,
                "mean": mean,
                "pattern_strength": variance / mean,
            }

        return None

    def _calculate_pattern_statistics(
        self,
        temporal_patterns: List[Dict[str, Any]],
        spatial_patterns: List[Dict[str, Any]],
        phase_patterns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate pattern statistics.

        Physical Meaning:
            Calculates statistical measures of the detected
            patterns for analysis.

        Args:
            temporal_patterns (List[Dict[str, Any]]): Temporal patterns.
            spatial_patterns (List[Dict[str, Any]]): Spatial patterns.
            phase_patterns (List[Dict[str, Any]]): Phase patterns.

        Returns:
            Dict[str, Any]: Pattern statistics.
        """
        return {
            "num_temporal_patterns": len(temporal_patterns),
            "num_spatial_patterns": len(spatial_patterns),
            "num_phase_patterns": len(phase_patterns),
            "total_patterns": len(temporal_patterns)
            + len(spatial_patterns)
            + len(phase_patterns),
        }

    def calculate_statistical_measures(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate statistical measures of the envelope field.

        Physical Meaning:
            Calculates various statistical measures to characterize
            the envelope field and its beating properties.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Statistical measures.
        """
        self.logger.info("Calculating statistical measures")

        # Calculate basic statistics
        basic_stats = self._calculate_basic_statistics(envelope)

        # Calculate higher-order moments
        higher_moments = self._calculate_higher_moments(envelope)

        # Calculate spectral statistics
        spectral_stats = self._calculate_spectral_statistics(envelope)

        results = {
            "basic_statistics": basic_stats,
            "higher_moments": higher_moments,
            "spectral_statistics": spectral_stats,
        }

        self.logger.info("Statistical measures calculated")
        return results

    def _calculate_basic_statistics(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Calculate basic statistics of the envelope field.

        Physical Meaning:
            Calculates basic statistical measures to characterize
            the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, float]: Basic statistics.
        """
        return {
            "mean": float(np.mean(envelope)),
            "std": float(np.std(envelope)),
            "min": float(np.min(envelope)),
            "max": float(np.max(envelope)),
            "median": float(np.median(envelope)),
        }

    def _calculate_higher_moments(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Calculate higher-order moments of the envelope field.

        Physical Meaning:
            Calculates higher-order moments to characterize
            the distribution of the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, float]: Higher-order moments.
        """
        from scipy import stats

        # Calculate skewness and kurtosis
        skewness = stats.skew(envelope.flatten())
        kurtosis = stats.kurtosis(envelope.flatten())

        return {"skewness": float(skewness), "kurtosis": float(kurtosis)}

    def _calculate_spectral_statistics(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Calculate spectral statistics of the envelope field.

        Physical Meaning:
            Calculates spectral statistics to characterize
            the frequency content of the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, float]: Spectral statistics.
        """
        # Calculate FFT
        fft_result = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_result) ** 2

        return {
            "total_power": float(np.sum(power_spectrum)),
            "max_power": float(np.max(power_spectrum)),
            "mean_power": float(np.mean(power_spectrum)),
            "std_power": float(np.std(power_spectrum)),
        }
