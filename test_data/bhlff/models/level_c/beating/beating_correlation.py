"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating correlation analysis utilities for Level C.

This module implements correlation analysis functions for beating
analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore


class BeatingCorrelationAnalyzer:
    """
    Correlation analysis utilities for beating analysis.

    Physical Meaning:
        Provides correlation analysis functions for beating analysis,
        including autocorrelation, cross-correlation, and
        correlation statistics.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating correlation analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def calculate_correlation_analysis(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate correlation analysis of the envelope field.

        Physical Meaning:
            Calculates correlation measures between different
            parts of the envelope field to identify beating patterns.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Correlation analysis results.
        """
        self.logger.info("Calculating correlation analysis")

        # Calculate autocorrelation
        autocorrelation = self._calculate_autocorrelation(envelope)

        # Calculate cross-correlation
        cross_correlation = self._calculate_cross_correlation(envelope)

        # Calculate correlation statistics
        correlation_stats = self._calculate_correlation_statistics(
            autocorrelation, cross_correlation
        )

        results = {
            "autocorrelation": autocorrelation,
            "cross_correlation": cross_correlation,
            "correlation_stats": correlation_stats,
        }

        self.logger.info("Correlation analysis completed")
        return results

    def _calculate_autocorrelation(self, envelope: np.ndarray) -> np.ndarray:
        """
        Calculate autocorrelation of the envelope field.

        Physical Meaning:
            Calculates the autocorrelation function to identify
            periodic patterns and beating frequencies.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            np.ndarray: Autocorrelation function.
        """
        # Calculate autocorrelation
        autocorr = np.correlate(envelope.flatten(), envelope.flatten(), mode="full")

        # Normalize
        autocorr = autocorr / np.max(autocorr)

        return autocorr

    def _calculate_cross_correlation(self, envelope: np.ndarray) -> np.ndarray:
        """
        Calculate cross-correlation between different field components.

        Physical Meaning:
            Calculates cross-correlation between different
            components of the envelope field.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            np.ndarray: Cross-correlation function.
        """
        if envelope.ndim > 1:
            # Calculate cross-correlation between first two dimensions
            cross_corr = np.correlate(
                envelope[:, 0].flatten(), envelope[:, 1].flatten(), mode="full"
            )
        else:
            cross_corr = np.array([0.0])

        return cross_corr

    def _calculate_correlation_statistics(
        self, autocorrelation: np.ndarray, cross_correlation: np.ndarray
    ) -> Dict[str, float]:
        """
        Calculate correlation statistics.

        Physical Meaning:
            Calculates statistical measures of the correlation
            functions for analysis.

        Args:
            autocorrelation (np.ndarray): Autocorrelation function.
            cross_correlation (np.ndarray): Cross-correlation function.

        Returns:
            Dict[str, float]: Correlation statistics.
        """
        return {
            "autocorr_max": float(np.max(autocorrelation)),
            "autocorr_mean": float(np.mean(autocorrelation)),
            "cross_corr_max": float(np.max(cross_correlation)),
            "cross_corr_mean": float(np.mean(cross_correlation)),
        }

    def calculate_variance_analysis(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Calculate variance analysis of the envelope field.

        Physical Meaning:
            Calculates variance measures to identify regions
            of high variability that may indicate beating patterns.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Variance analysis results.
        """
        self.logger.info("Calculating variance analysis")

        # Calculate overall variance
        overall_variance = np.var(envelope)

        # Calculate local variance
        local_variance = self._calculate_local_variance(envelope)

        # Calculate variance statistics
        variance_stats = self._calculate_variance_statistics(
            overall_variance, local_variance
        )

        results = {
            "overall_variance": overall_variance,
            "local_variance": local_variance,
            "variance_stats": variance_stats,
        }

        self.logger.info("Variance analysis completed")
        return results

    def _calculate_local_variance(self, envelope: np.ndarray) -> np.ndarray:
        """
        Calculate local variance of the envelope field.

        Physical Meaning:
            Calculates local variance to identify regions
            of high variability.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            np.ndarray: Local variance array.
        """
        # Calculate local variance using a sliding window
        window_size = min(10, len(envelope.flatten()) // 10)
        local_var = np.zeros_like(envelope.flatten())

        for i in range(len(envelope.flatten())):
            start = max(0, i - window_size // 2)
            end = min(len(envelope.flatten()), i + window_size // 2 + 1)
            local_var[i] = np.var(envelope.flatten()[start:end])

        return local_var.reshape(envelope.shape)

    def _calculate_variance_statistics(
        self, overall_variance: float, local_variance: np.ndarray
    ) -> Dict[str, float]:
        """
        Calculate variance statistics.

        Physical Meaning:
            Calculates statistical measures of the variance
            for analysis.

        Args:
            overall_variance (float): Overall variance.
            local_variance (np.ndarray): Local variance array.

        Returns:
            Dict[str, float]: Variance statistics.
        """
        return {
            "overall_variance": overall_variance,
            "local_variance_max": float(np.max(local_variance)),
            "local_variance_mean": float(np.mean(local_variance)),
            "local_variance_std": float(np.std(local_variance)),
        }
