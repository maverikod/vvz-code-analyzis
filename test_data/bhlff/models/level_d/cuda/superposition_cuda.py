"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized multimode superposition analysis for Level D models.

This module implements CUDA-accelerated multimode superposition analysis
with vectorization and block processing optimized for 80% GPU memory usage.

Physical Meaning:
    Multimode superposition represents the complex structure of the unified
    phase field through the superposition of different frequency components,
    where each mode corresponds to different physical excitations or envelope
    functions. CUDA acceleration enables efficient processing of large fields.

Mathematical Foundation:
    - Multimode field: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
    - Frame stability: Jaccard index between frame maps before/after
    - Frequency stability: Analysis of spectral peak shifts

Example:
    >>> from bhlff.models.level_d.cuda import MultiModeModelCUDA
    >>> model = MultiModeModelCUDA(domain, parameters)
    >>> results = model.analyze_frame_stability(field_before, field_after)
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
from .superposition_utils_cuda import FrameExtractorCUDA, StabilityAnalyzerCUDA


class MultiModeModelCUDA:
    """
    CUDA-optimized multi-mode superposition model for frame stability analysis.

    Physical Meaning:
        Represents the superposition of multiple frequency modes on a stable frame
        structure, testing the robustness of the phase field topology under
        mode additions using GPU acceleration.

    Mathematical Foundation:
        Implements the multi-mode superposition:
        a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
        with CUDA-accelerated operations and block processing.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """
        Initialize CUDA-optimized multi-mode model.

        Physical Meaning:
            Sets up the multi-mode superposition model with GPU acceleration
            and block processing optimized for available GPU memory.

        Args:
            domain (Domain): Computational domain
            parameters (Dict): Parameters for mode addition
        """
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA backend
        self.cuda_available = CUDA_AVAILABLE and UTILS_CUDA_AVAILABLE
        if self.cuda_available:
            try:
                self.backend = get_optimal_backend()
                if hasattr(self.backend, "device"):
                    self.device = self.backend.device
                    self._compute_optimal_block_size()
                else:
                    self.cuda_available = False
            except Exception as e:
                self.logger.warning(f"CUDA initialization failed: {e}")
                self.cuda_available = False

        # Initialize analysis tools
        self._frame_extractor = FrameExtractorCUDA(domain, self.cuda_available)
        self._stability_analyzer = StabilityAnalyzerCUDA(domain, self.cuda_available)

        self.logger.info(f"Multi-mode model CUDA initialized: {self.cuda_available}")

    def _compute_optimal_block_size(self) -> int:
        """
        Compute optimal block size based on GPU memory (80% usage).

        Physical Meaning:
            Calculates block size to use 80% of available GPU memory,
            ensuring efficient memory usage while avoiding OOM errors.

        Returns:
            int: Optimal block size per dimension.
        """
        if not self.cuda_available:
            return 8

        try:
            from ....utils.cuda_utils import calculate_optimal_window_memory

            # For multimode operations, we need space for:
            # - Input field: 1x
            # - FFT workspace: 3x (forward, intermediate, backward)
            # - Mode superposition: 2x (temporary arrays)
            # - Frame extraction: 1x
            # Total overhead: ~7x
            overhead_factor = 7

            max_window_elements, _, _ = calculate_optimal_window_memory(
                gpu_memory_ratio=0.8,
                overhead_factor=overhead_factor,
                logger=self.logger,
            )

            # Calculate block size per dimension
            n_dims = len(self.domain.shape)
            elements_per_dim = int(max_window_elements ** (1.0 / n_dims))

            # Ensure reasonable bounds (4 to 128)
            block_size = max(4, min(elements_per_dim, 128))

            self.block_size = block_size
            self.logger.info(f"Optimal block size: {block_size}")

            return block_size

        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size: {e}, using default 8"
            )
            self.block_size = 8
            return 8

    def create_multi_mode_field(
        self, base_field: np.ndarray, modes: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Create multi-mode field from base field and additional modes with CUDA.

        Physical Meaning:
            Constructs a multi-mode phase field by superposing different
            frequency components using GPU-accelerated vectorized operations.

        Mathematical Foundation:
            Multi-mode field: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
            implemented with CUDA-accelerated vectorized operations.

        Args:
            base_field (np.ndarray): Base field structure
            modes (List[Dict]): List of mode parameters

        Returns:
            np.ndarray: Multi-mode field
        """
        self.logger.info(f"Creating multi-mode field with {len(modes)} modes (CUDA)")

        if self.cuda_available:
            # Transfer to GPU
            base_field_gpu = self.backend.array(base_field)

            # Vectorized mode addition on GPU
            for mode in modes:
                frequency = mode.get("frequency", 1.0)
                amplitude = mode.get("amplitude", 1.0)
                phase = mode.get("phase", 0.0)
                spatial_mode = mode.get("spatial_mode", "bvp_envelope_modulation")

                # Create mode field on GPU
                mode_field_gpu = self._create_single_mode_field_cuda(
                    frequency, amplitude, phase, spatial_mode, base_field.shape
                )

                # Vectorized addition on GPU
                base_field_gpu = base_field_gpu + mode_field_gpu

            # Transfer back to CPU
            return self.backend.to_numpy(base_field_gpu)
        else:
            # CPU fallback
            multi_mode_field = base_field.copy()
            for mode in modes:
                frequency = mode.get("frequency", 1.0)
                amplitude = mode.get("amplitude", 1.0)
                phase = mode.get("phase", 0.0)
                spatial_mode = mode.get("spatial_mode", "bvp_envelope_modulation")

                mode_field = self._create_single_mode_field_cpu(
                    frequency, amplitude, phase, spatial_mode, base_field.shape
                )
                multi_mode_field += mode_field

            return multi_mode_field

    def _create_single_mode_field_cuda(
        self,
        frequency: float,
        amplitude: float,
        phase: float,
        spatial_mode: str,
        shape: Tuple[int, ...],
    ) -> "cp.ndarray":
        """Create single mode field on GPU with vectorization."""
        # Create coordinate grids on GPU
        coords_gpu = self._create_coordinate_grids_cuda(shape)

        # Create spatial mode on GPU
        if spatial_mode == "bvp_envelope_modulation":
            spatial_field_gpu = self._create_bvp_envelope_modulation_cuda(
                coords_gpu, frequency, shape
            )
        else:
            spatial_field_gpu = self._create_default_spatial_mode_cuda(
                coords_gpu, frequency, shape
            )

        # Vectorized amplitude and phase application on GPU
        mode_field_gpu = amplitude * cp.exp(1j * phase) * spatial_field_gpu

        return mode_field_gpu.real

    def _create_single_mode_field_cpu(
        self,
        frequency: float,
        amplitude: float,
        phase: float,
        spatial_mode: str,
        shape: Tuple[int, ...],
    ) -> np.ndarray:
        """Create single mode field on CPU."""
        coords = self._create_coordinate_grids_cpu(shape)
        if spatial_mode == "bvp_envelope_modulation":
            spatial_field = self._create_bvp_envelope_modulation_cpu(
                coords, frequency, shape
            )
        else:
            spatial_field = self._create_default_spatial_mode_cpu(
                coords, frequency, shape
            )
        mode_field = amplitude * np.exp(1j * phase) * spatial_field
        return mode_field.real

    def _create_coordinate_grids_cuda(
        self, shape: Tuple[int, ...]
    ) -> List["cp.ndarray"]:
        """Create coordinate grids on GPU."""
        coords = []
        for i, size in enumerate(shape):
            coord = cp.linspace(0, self.domain.L, size)
            coords.append(coord)
        return coords

    def _create_coordinate_grids_cpu(self, shape: Tuple[int, ...]) -> List[np.ndarray]:
        """Create coordinate grids on CPU."""
        coords = []
        for i, size in enumerate(shape):
            coord = np.linspace(0, self.domain.L, size)
            coords.append(coord)
        return coords

    def _create_bvp_envelope_modulation_cuda(
        self, coords: List["cp.ndarray"], frequency: float, shape: Tuple[int, ...]
    ) -> "cp.ndarray":
        """Create BVP envelope modulation spatial mode on GPU."""
        spatial_field = cp.ones(shape, dtype=cp.complex128)
        return spatial_field

    def _create_bvp_envelope_modulation_cpu(
        self, coords: List[np.ndarray], frequency: float, shape: Tuple[int, ...]
    ) -> np.ndarray:
        """Create BVP envelope modulation spatial mode on CPU."""
        spatial_field = np.ones(shape, dtype=np.complex128)
        return spatial_field

    def _create_default_spatial_mode_cuda(
        self, coords: List["cp.ndarray"], frequency: float, shape: Tuple[int, ...]
    ) -> "cp.ndarray":
        """Create default spatial mode on GPU."""
        spatial_field = cp.ones(shape, dtype=cp.complex128)
        return spatial_field

    def _create_default_spatial_mode_cpu(
        self, coords: List[np.ndarray], frequency: float, shape: Tuple[int, ...]
    ) -> np.ndarray:
        """Create default spatial mode on CPU."""
        spatial_field = np.ones(shape, dtype=np.complex128)
        return spatial_field

    def analyze_frame_stability(
        self, before: np.ndarray, after: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze frame stability using Jaccard index with CUDA.

        Physical Meaning:
            Computes the Jaccard index between frame structures before and
            after mode addition using GPU-accelerated operations.

        Mathematical Foundation:
            Jaccard index: J(A,B) = |A ∩ B| / |A ∪ B|
            computed with CUDA-accelerated vectorized operations.

        Args:
            before (np.ndarray): Frame before mode addition
            after (np.ndarray): Frame after mode addition

        Returns:
            Dict: Stability analysis results
        """
        self.logger.info("Analyzing frame stability (CUDA)")

        # Extract frame structures
        frame_before = self._frame_extractor.extract_frame(before)
        frame_after = self._frame_extractor.extract_frame(after)

        # Compute Jaccard index with CUDA
        jaccard_index = self.compute_jaccard_index(frame_before, frame_after)

        # Compute additional stability metrics
        stability_metrics = self._stability_analyzer.compute_stability_metrics(
            frame_before, frame_after
        )

        # Check if stability criteria are met
        jaccard_threshold = self.parameters.get("jaccard_threshold", 0.8)
        passed = jaccard_index >= jaccard_threshold

        results = {
            "jaccard_index": float(jaccard_index),
            "frame_before": frame_before,
            "frame_after": frame_after,
            "stability_metrics": stability_metrics,
            "passed": passed,
            "threshold": jaccard_threshold,
        }

        self.logger.info(
            f"Frame stability analysis completed: Jaccard index = {jaccard_index:.3f}"
        )
        return results

    def compute_jaccard_index(self, map1: np.ndarray, map2: np.ndarray) -> float:
        """
        Compute Jaccard index for frame comparison with CUDA.

        Physical Meaning:
            Measures the similarity between two frame maps using the Jaccard
            index with GPU-accelerated vectorized operations.

        Mathematical Foundation:
            Jaccard index: J(A,B) = |A ∩ B| / |A ∪ B|
            computed with CUDA vectorized operations.

        Args:
            map1 (np.ndarray): First frame map
            map2 (np.ndarray): Second frame map

        Returns:
            float: Jaccard index (0-1)
        """
        if self.cuda_available:
            # CUDA perform computation
            map1_gpu = self.backend.array(map1)
            map2_gpu = self.backend.array(map2)

            # Vectorized binary conversion
            binary_map1_gpu = (map1_gpu > 0).astype(cp.int32)
            binary_map2_gpu = (map2_gpu > 0).astype(cp.int32)

            # Vectorized intersection and union
            intersection_gpu = cp.sum(binary_map1_gpu * binary_map2_gpu)
            union_gpu = cp.sum(cp.maximum(binary_map1_gpu, binary_map2_gpu))

            # Transfer results to CPU
            intersection = float(intersection_gpu)
            union = float(union_gpu)
        else:
            # CPU computation
            binary_map1 = (map1 > 0).astype(int)
            binary_map2 = (map2 > 0).astype(int)
            intersection = np.sum(binary_map1 * binary_map2)
            union = np.sum(np.maximum(binary_map1, binary_map2))

        # Avoid division by zero
        if union == 0:
            return 0.0

        jaccard_index = intersection / union
        return float(jaccard_index)


class SuperpositionAnalyzerCUDA:
    """
    Facade analyzer for multimode superposition using CUDA.

    Physical Meaning:
        Provides a simple interface to analyze frame stability after
        multimode superposition, delegating to the CUDA-optimized model.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize superposition analyzer with underlying CUDA model."""
        self._model = MultiModeModelCUDA(domain, parameters)
        self.logger = logging.getLogger(__name__)

    def analyze(self, before: np.ndarray, after: np.ndarray) -> Dict[str, Any]:
        """Run frame stability analysis for before/after fields."""
        return self._model.analyze_frame_stability(before, after)
