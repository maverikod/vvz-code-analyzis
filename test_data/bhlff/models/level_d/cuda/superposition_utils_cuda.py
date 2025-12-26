"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized utility classes for superposition analysis.

This module provides CUDA-accelerated utility classes for frame extraction
and stability analysis in multimode superposition.

Physical Meaning:
    Provides GPU-accelerated utilities for extracting frame structures
    and computing stability metrics for phase field topology analysis.
"""

import numpy as np
from typing import Dict, Any
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class FrameExtractorCUDA:
    """CUDA-optimized frame extractor."""

    def __init__(self, domain: "Domain", cuda_available: bool = False):
        """Initialize CUDA frame extractor."""
        self.domain = domain
        self.cuda_available = cuda_available
        if cuda_available:
            try:
                from bhlff.utils.cuda_utils import get_optimal_backend

                self.backend = get_optimal_backend()
            except Exception:
                self.cuda_available = False

    def extract_frame(self, field: np.ndarray) -> np.ndarray:
        """
        Extract frame structure from field with CUDA.

        Physical Meaning:
            Extracts frame structure using hot zones method with
            GPU-accelerated percentile computation.

        Args:
            field (np.ndarray): Input field

        Returns:
            np.ndarray: Frame structure
        """
        if self.cuda_available:
            field_gpu = self.backend.array(field)
            threshold_gpu = cp.percentile(cp.abs(field_gpu), 80)
            frame_gpu = (cp.abs(field_gpu) > threshold_gpu).astype(cp.float64)
            return self.backend.to_numpy(frame_gpu)
        else:
            threshold = np.percentile(np.abs(field), 80)
            frame = (np.abs(field) > threshold).astype(float)
            return frame


class StabilityAnalyzerCUDA:
    """CUDA-optimized stability analyzer."""

    def __init__(self, domain: "Domain", cuda_available: bool = False):
        """Initialize CUDA stability analyzer."""
        self.domain = domain
        self.cuda_available = cuda_available
        if cuda_available:
            try:
                from bhlff.utils.cuda_utils import get_optimal_backend

                self.backend = get_optimal_backend()
            except Exception:
                self.cuda_available = False

    def compute_stability_metrics(
        self, frame_before: np.ndarray, frame_after: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compute additional stability metrics with CUDA.

        Physical Meaning:
            Computes frame stability metrics using GPU-accelerated
            vectorized operations.

        Args:
            frame_before (np.ndarray): Frame before mode addition
            frame_after (np.ndarray): Frame after mode addition

        Returns:
            Dict: Stability metrics
        """
        if self.cuda_available:
            frame_before_gpu = self.backend.array(frame_before)
            frame_after_gpu = self.backend.array(frame_after)

            # Vectorized overlap computation
            overlap_gpu = cp.sum(frame_before_gpu * frame_after_gpu)
            changes_gpu = cp.sum(cp.abs(frame_after_gpu - frame_before_gpu))

            overlap = float(overlap_gpu)
            changes = float(changes_gpu)
        else:
            overlap = np.sum(frame_before * frame_after)
            changes = np.sum(np.abs(frame_after - frame_before))

        # Compute stability ratio
        stability_ratio = (
            overlap / (overlap + changes) if (overlap + changes) > 0 else 0.0
        )

        return {
            "overlap": float(overlap),
            "changes": float(changes),
            "stability_ratio": float(stability_ratio),
        }
