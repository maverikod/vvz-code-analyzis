"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Collective modes spectrum analysis module.

This module implements spectrum analysis functionality for collective modes
in multi-particle systems in Level F of 7D phase field theory.

Physical Meaning:
    Analyzes mode spectrum including frequency distribution,
    spectral features, and mode spacing.

Example:
    >>> spectrum_analyzer = CollectiveModesSpectrumAnalyzer(domain, particles, system_params)
    >>> spectrum = spectrum_analyzer.analyze_mode_spectrum(modes)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import Particle, SystemParameters


class CollectiveModesSpectrumAnalyzer:
    """
    Collective modes spectrum analyzer for multi-particle systems.

    Physical Meaning:
        Analyzes mode spectrum including frequency distribution,
        spectral features, and mode spacing.

    Mathematical Foundation:
        Implements spectrum analysis:
        - Frequency distribution analysis
        - Spectral features analysis
        - Mode spacing analysis
    """

    def __init__(
        self, domain, particles: List[Particle], system_params: SystemParameters
    ):
        """
        Initialize collective modes spectrum analyzer.

        Physical Meaning:
            Sets up the spectrum analysis system with
            domain, particles, and system parameters.

        Args:
            domain: Domain parameters.
            particles (List[Particle]): List of particles.
            system_params (SystemParameters): System parameters.
        """
        self.domain = domain
        self.particles = particles
        self.system_params = system_params
        self.logger = logging.getLogger(__name__)

    def analyze_mode_spectrum(self, modes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze mode spectrum.

        Physical Meaning:
            Analyzes mode spectrum including frequency distribution,
            spectral features, and mode spacing.

        Mathematical Foundation:
            Analyzes mode spectrum through:
            - Frequency distribution analysis
            - Spectral features analysis
            - Mode spacing analysis

        Args:
            modes (Dict[str, Any]): Collective modes analysis results.

        Returns:
            Dict[str, Any]: Mode spectrum analysis results.
        """
        self.logger.info("Analyzing mode spectrum")

        # Extract frequencies from modes
        eigenvalues = modes.get("eigenvalues", np.array([]))
        frequencies = np.sqrt(np.abs(eigenvalues))

        # Analyze frequency distribution
        frequency_distribution = self._analyze_frequency_distribution(frequencies)

        # Analyze spectral features
        spectral_features = self._analyze_spectral_features(frequencies)

        # Find spectral gaps
        spectral_gaps = self._find_spectral_gaps(frequencies)

        # Find spectral clusters
        spectral_clusters = self._find_spectral_clusters(frequencies)

        # Find spectral peaks
        spectral_peaks = self._find_spectral_peaks(frequencies)

        # Analyze mode spacing
        mode_spacing = self._analyze_mode_spacing(frequencies)

        results = {
            "frequency_distribution": frequency_distribution,
            "spectral_features": spectral_features,
            "spectral_gaps": spectral_gaps,
            "spectral_clusters": spectral_clusters,
            "spectral_peaks": spectral_peaks,
            "mode_spacing": mode_spacing,
            "spectrum_analysis_complete": True,
        }

        self.logger.info("Mode spectrum analyzed")
        return results

    def _analyze_frequency_distribution(
        self, frequencies: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze frequency distribution.

        Physical Meaning:
            Analyzes frequency distribution of collective modes
            in multi-particle system.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            Dict[str, Any]: Frequency distribution analysis results.
        """
        # Calculate frequency statistics
        frequency_statistics = {
            "mean_frequency": np.mean(frequencies),
            "std_frequency": np.std(frequencies),
            "min_frequency": np.min(frequencies),
            "max_frequency": np.max(frequencies),
            "frequency_range": np.max(frequencies) - np.min(frequencies),
        }

        # Calculate frequency histogram
        frequency_histogram, frequency_bins = np.histogram(frequencies, bins=20)

        return {
            "frequency_statistics": frequency_statistics,
            "frequency_histogram": frequency_histogram,
            "frequency_bins": frequency_bins,
        }

    def _analyze_spectral_features(self, frequencies: np.ndarray) -> Dict[str, Any]:
        """
        Analyze spectral features.

        Physical Meaning:
            Analyzes spectral features of collective modes
            including peaks, valleys, and transitions.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            Dict[str, Any]: Spectral features analysis results.
        """
        # Calculate spectral features
        spectral_features = {
            "spectral_density": self._calculate_spectral_density(frequencies),
            "spectral_entropy": self._calculate_spectral_entropy(frequencies),
            "spectral_skewness": self._calculate_spectral_skewness(frequencies),
            "spectral_kurtosis": self._calculate_spectral_kurtosis(frequencies),
        }

        return spectral_features

    def _calculate_spectral_density(self, frequencies: np.ndarray) -> float:
        """
        Calculate spectral density.

        Physical Meaning:
            Calculates spectral density of collective modes
            based on frequency distribution.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            float: Spectral density measure.
        """
        # Simplified spectral density calculation
        # In practice, this would involve proper density calculation
        if len(frequencies) > 0:
            frequency_range = np.max(frequencies) - np.min(frequencies)
            spectral_density = (
                len(frequencies) / frequency_range if frequency_range > 0 else 0.0
            )
        else:
            spectral_density = 0.0

        return spectral_density

    def _calculate_spectral_entropy(self, frequencies: np.ndarray) -> float:
        """
        Calculate spectral entropy.

        Physical Meaning:
            Calculates spectral entropy of collective modes
            based on frequency distribution.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            float: Spectral entropy measure.
        """
        # Simplified spectral entropy calculation
        # In practice, this would involve proper entropy calculation
        if len(frequencies) > 0:
            # Calculate histogram
            histogram, _ = np.histogram(frequencies, bins=20)
            histogram = histogram / np.sum(histogram)  # Normalize

            # Calculate entropy
            entropy = -np.sum(histogram * np.log(histogram + 1e-10))
        else:
            entropy = 0.0

        return entropy

    def _calculate_spectral_skewness(self, frequencies: np.ndarray) -> float:
        """
        Calculate spectral skewness.

        Physical Meaning:
            Calculates spectral skewness of collective modes
            based on frequency distribution.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            float: Spectral skewness measure.
        """
        # Simplified spectral skewness calculation
        # In practice, this would involve proper skewness calculation
        if len(frequencies) > 0:
            mean_freq = np.mean(frequencies)
            std_freq = np.std(frequencies)
            skewness = (
                np.mean(((frequencies - mean_freq) / std_freq) ** 3)
                if std_freq > 0
                else 0.0
            )
        else:
            skewness = 0.0

        return skewness

    def _calculate_spectral_kurtosis(self, frequencies: np.ndarray) -> float:
        """
        Calculate spectral kurtosis.

        Physical Meaning:
            Calculates spectral kurtosis of collective modes
            based on frequency distribution.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            float: Spectral kurtosis measure.
        """
        # Simplified spectral kurtosis calculation
        # In practice, this would involve proper kurtosis calculation
        if len(frequencies) > 0:
            mean_freq = np.mean(frequencies)
            std_freq = np.std(frequencies)
            kurtosis = (
                np.mean(((frequencies - mean_freq) / std_freq) ** 4)
                if std_freq > 0
                else 0.0
            )
        else:
            kurtosis = 0.0

        return kurtosis

    def _find_spectral_gaps(self, frequencies: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find spectral gaps.

        Physical Meaning:
            Finds spectral gaps in collective modes spectrum
            where modes are missing or sparse.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            List[Dict[str, Any]]: Spectral gaps.
        """
        # Simplified spectral gap finding
        # In practice, this would involve proper gap analysis
        gaps = []

        if len(frequencies) > 1:
            sorted_frequencies = np.sort(frequencies)
            frequency_differences = np.diff(sorted_frequencies)

            # Find gaps (large differences)
            gap_threshold = np.mean(frequency_differences) + 2 * np.std(
                frequency_differences
            )

            for i, diff in enumerate(frequency_differences):
                if diff > gap_threshold:
                    gap = {
                        "start_frequency": sorted_frequencies[i],
                        "end_frequency": sorted_frequencies[i + 1],
                        "gap_size": diff,
                        "gap_index": i,
                    }
                    gaps.append(gap)

        return gaps

    def _find_spectral_clusters(self, frequencies: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find spectral clusters.

        Physical Meaning:
            Finds spectral clusters in collective modes spectrum
            where modes are grouped together.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            List[Dict[str, Any]]: Spectral clusters.
        """
        # Simplified spectral cluster finding
        # In practice, this would involve proper clustering analysis
        clusters = []

        if len(frequencies) > 1:
            sorted_frequencies = np.sort(frequencies)
            frequency_differences = np.diff(sorted_frequencies)

            # Find clusters (small differences)
            cluster_threshold = np.mean(frequency_differences) - np.std(
                frequency_differences
            )

            current_cluster = [sorted_frequencies[0]]
            for i, diff in enumerate(frequency_differences):
                if diff < cluster_threshold:
                    current_cluster.append(sorted_frequencies[i + 1])
                else:
                    if len(current_cluster) > 1:
                        cluster = {
                            "frequencies": current_cluster,
                            "cluster_size": len(current_cluster),
                            "cluster_center": np.mean(current_cluster),
                            "cluster_width": np.max(current_cluster)
                            - np.min(current_cluster),
                        }
                        clusters.append(cluster)
                    current_cluster = [sorted_frequencies[i + 1]]

            # Add last cluster if it has multiple elements
            if len(current_cluster) > 1:
                cluster = {
                    "frequencies": current_cluster,
                    "cluster_size": len(current_cluster),
                    "cluster_center": np.mean(current_cluster),
                    "cluster_width": np.max(current_cluster) - np.min(current_cluster),
                }
                clusters.append(cluster)

        return clusters

    def _find_spectral_peaks(self, frequencies: np.ndarray) -> List[Dict[str, Any]]:
        """
        Find spectral peaks.

        Physical Meaning:
            Finds spectral peaks in collective modes spectrum
            where modes are concentrated.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            List[Dict[str, Any]]: Spectral peaks.
        """
        # Simplified spectral peak finding
        # In practice, this would involve proper peak analysis
        peaks = []

        if len(frequencies) > 0:
            # Calculate histogram
            histogram, bins = np.histogram(frequencies, bins=20)
            bin_centers = (bins[:-1] + bins[1:]) / 2

            # Find peaks in histogram
            for i in range(1, len(histogram) - 1):
                if (
                    histogram[i] > histogram[i - 1]
                    and histogram[i] > histogram[i + 1]
                    and histogram[i] > np.mean(histogram)
                ):
                    peak = {
                        "frequency": bin_centers[i],
                        "peak_height": histogram[i],
                        "peak_index": i,
                    }
                    peaks.append(peak)

        return peaks

    def _analyze_mode_spacing(self, frequencies: np.ndarray) -> Dict[str, Any]:
        """
        Analyze mode spacing.

        Physical Meaning:
            Analyzes spacing between collective modes
            in frequency spectrum.

        Args:
            frequencies (np.ndarray): Mode frequencies.

        Returns:
            Dict[str, Any]: Mode spacing analysis results.
        """
        # Calculate mode spacing
        if len(frequencies) > 1:
            sorted_frequencies = np.sort(frequencies)
            spacing = np.diff(sorted_frequencies)

            spacing_analysis = {
                "mean_spacing": np.mean(spacing),
                "std_spacing": np.std(spacing),
                "min_spacing": np.min(spacing),
                "max_spacing": np.max(spacing),
                "spacing_regularity": (
                    1.0 / (1.0 + np.std(spacing) / np.mean(spacing))
                    if np.mean(spacing) > 0
                    else 0.0
                ),
            }
        else:
            spacing_analysis = {
                "mean_spacing": 0.0,
                "std_spacing": 0.0,
                "min_spacing": 0.0,
                "max_spacing": 0.0,
                "spacing_regularity": 0.0,
            }

        return spacing_analysis
