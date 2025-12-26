"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized field projection analysis for Level D models.

This module implements CUDA-accelerated field projection analysis onto different
interaction windows with vectorization and block processing optimized for 80% GPU memory.

Physical Meaning:
    Field projections separate the unified phase field into different
    interaction regimes based on frequency and amplitude characteristics:
    - EM field: Phase gradients (U(1) symmetry), long-range interactions
    - Strong field: High-Q localized modes, short-range interactions
    - Weak field: Chiral combinations, parity-breaking interactions

Mathematical Foundation:
    - EM projection: P_EM[a] = FFT⁻¹[FFT(a) × H_EM(ω)]
    - Strong projection: P_STRONG[a] = FFT⁻¹[FFT(a) × H_STRONG(ω)]
    - Weak projection: P_WEAK[a] = FFT⁻¹[FFT(a) × H_WEAK(ω)]
    All implemented with CUDA-accelerated FFT and vectorized filtering.

Example:
    >>> from bhlff.models.level_d.cuda import FieldProjectionCUDA
    >>> projection = FieldProjectionCUDA(field, window_params)
    >>> results = projection.project_field_windows()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

try:
    import cupy as cp
    import cupyx.scipy.fft as cp_fft

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None
    cp_fft = None

from bhlff.utils.cuda_utils import (
    get_optimal_backend,
    CUDA_AVAILABLE as UTILS_CUDA_AVAILABLE,
)
from .projectors_cuda import EMProjectorCUDA, StrongProjectorCUDA, WeakProjectorCUDA
from .signature_analyzer_cuda import SignatureAnalyzerCUDA


class FieldProjectionCUDA:
    """
    CUDA-optimized field projection onto different interaction windows.

    Physical Meaning:
        Projects the unified phase field onto different frequency
        windows using GPU-accelerated FFT and vectorized filtering.

    Mathematical Foundation:
        Uses CUDA-accelerated frequency-domain filtering to separate
        different interaction regimes based on their characteristic
        frequency and amplitude signatures.
    """

    def __init__(self, field: np.ndarray, projection_params: Dict[str, Any]):
        """
        Initialize CUDA-optimized field projection.

        Physical Meaning:
            Sets up the field projection system for separating
            the unified phase field into different interaction
            regimes using GPU acceleration.

        Args:
            field (np.ndarray): Input phase field
            projection_params (Dict): Projection parameters
        """
        self.field = field
        self.projection_params = projection_params
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA backend
        self.cuda_available = CUDA_AVAILABLE and UTILS_CUDA_AVAILABLE
        if self.cuda_available:
            try:
                self.backend = get_optimal_backend()
                self._compute_optimal_block_size()
            except Exception as e:
                self.logger.warning(f"CUDA initialization failed: {e}")
                self.cuda_available = False

        # Initialize projectors
        self._em_projector = EMProjectorCUDA(
            projection_params.get("em", {}),
            self.cuda_available,
            self.backend if self.cuda_available else None,
        )
        self._strong_projector = StrongProjectorCUDA(
            projection_params.get("strong", {}),
            self.cuda_available,
            self.backend if self.cuda_available else None,
        )
        self._weak_projector = WeakProjectorCUDA(
            projection_params.get("weak", {}),
            self.cuda_available,
            self.backend if self.cuda_available else None,
        )

        # Initialize signature analyzer
        self._signature_analyzer = SignatureAnalyzerCUDA(
            self.cuda_available, self.backend if self.cuda_available else None
        )

        self.logger.info(f"Field projection CUDA initialized: {self.cuda_available}")

    def _compute_optimal_block_size(self) -> int:
        """
        Compute optimal block size based on GPU memory (80% usage).

        Returns:
            int: Optimal block size per dimension.
        """
        if not self.cuda_available:
            self.block_size = 8
            return 8

        try:
            mem_info = self.backend.get_memory_info()
            free_memory_bytes = mem_info["free_memory"]
            available_memory_bytes = int(free_memory_bytes * 0.8)

            bytes_per_element = 16
            # For projections: input, FFT, filter, output = ~4x overhead
            overhead_factor = 4

            max_elements = available_memory_bytes // (
                bytes_per_element * overhead_factor
            )

            n_dims = len(self.field.shape) if hasattr(self.field, "shape") else 3
            elements_per_dim = int(max_elements ** (1.0 / n_dims))
            block_size = max(4, min(elements_per_dim, 128))

            self.block_size = block_size
            self.logger.info(
                f"Optimal block size for projections: {block_size} "
                f"(using 80% of {available_memory_bytes / 1e9:.2f} GB GPU memory)"
            )
            return block_size
        except Exception as e:
            self.logger.warning(f"Failed to compute optimal block size: {e}")
            self.block_size = 8
            return 8

    def project_em_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto electromagnetic window with CUDA.

        Physical Meaning:
            Extracts the electromagnetic component using GPU-accelerated
            FFT and bandpass filtering.

        Mathematical Foundation:
            EM_field = FFT⁻¹[FFT(field) × H_EM(ω)] on GPU.

        Args:
            field (np.ndarray): Input field

        Returns:
            np.ndarray: EM field projection
        """
        return self._em_projector.project(field)

    def project_strong_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto strong interaction window with CUDA.

        Physical Meaning:
            Extracts the strong interaction component using GPU-accelerated
            FFT and high-Q filtering.

        Args:
            field (np.ndarray): Input field

        Returns:
            np.ndarray: Strong field projection
        """
        return self._strong_projector.project(field)

    def project_weak_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto weak interaction window with CUDA.

        Physical Meaning:
            Extracts the weak interaction component using GPU-accelerated
            FFT and chiral filtering.

        Args:
            field (np.ndarray): Input field

        Returns:
            np.ndarray: Weak field projection
        """
        return self._weak_projector.project(field)

    def project_field_windows(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Project fields onto different frequency-amplitude windows with CUDA.

        Physical Meaning:
            Separates the unified phase field into different interaction
            regimes using GPU-accelerated operations.

        Args:
            field (np.ndarray): Input field

        Returns:
            Dict: Projected fields and signatures
        """
        self.logger.info("Projecting fields onto interaction windows (CUDA)")

        # Project onto each window
        em_projection = self.project_em_field(field)
        strong_projection = self.project_strong_field(field)
        weak_projection = self.project_weak_field(field)

        # Analyze field signatures
        signatures = self._signature_analyzer.analyze_field_signatures(
            {"em": em_projection, "strong": strong_projection, "weak": weak_projection}
        )

        results = {
            "em_projection": em_projection,
            "strong_projection": strong_projection,
            "weak_projection": weak_projection,
            "signatures": signatures,
        }

        self.logger.info("Field projection completed")
        return results


class ProjectionAnalyzerCUDA:
    """
    CUDA-optimized analyzer for field projections onto interaction windows.

    Physical Meaning:
        Analyzes field projections using GPU-accelerated operations
        to understand the field structure and dynamics in different
        interaction regimes.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize CUDA projection analyzer."""
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA backend
        self.cuda_available = CUDA_AVAILABLE and UTILS_CUDA_AVAILABLE
        if self.cuda_available:
            try:
                self.backend = get_optimal_backend()
            except Exception:
                self.cuda_available = False

    def project_field_windows(
        self, field: np.ndarray, window_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Project fields onto different frequency-amplitude windows with CUDA.

        Args:
            field (np.ndarray): Input field
            window_params (Dict): Window parameters

        Returns:
            Dict: Projection analysis results
        """
        # Create CUDA-optimized field projection
        projection = FieldProjectionCUDA(field, window_params)

        # Perform projections
        results = projection.project_field_windows(field)

        return results
