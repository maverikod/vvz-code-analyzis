"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized superposition analyzer for Level D models.

This module implements CUDA-accelerated superposition analysis with
vectorization for identifying dominant frequency modes.

Physical Meaning:
    Analyzes the superposition of multiple frequency modes in the phase
    field using GPU-accelerated FFT and vectorized operations to identify
    dominant modes and their characteristics.

Mathematical Foundation:
    Uses CUDA FFT decomposition: a(x) = Σ A_k e^(ik·x)
    where A_k are the mode amplitudes and k are wave vectors.
"""

import numpy as np
from typing import Dict, Any, List
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from bhlff.utils.cuda_utils import (
    get_optimal_backend,
    CUDA_AVAILABLE as UTILS_CUDA_AVAILABLE,
)


class SuperpositionAnalyzerCUDA:
    """
    CUDA-optimized analyzer for multimode superposition patterns.

    Physical Meaning:
        Analyzes the superposition of multiple frequency modes in the phase
        field using GPU-accelerated FFT and vectorized operations.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize CUDA superposition analyzer."""
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

    def analyze_superposition(
        self, field: np.ndarray, threshold: float = 0.1
    ) -> Dict[str, Any]:
        """
        Analyze multimode superposition patterns with CUDA FFT.

        Physical Meaning:
            Performs FFT analysis on GPU to decompose the field into
            its constituent modes and identifies dominant frequency
            components and their amplitudes.

        Mathematical Foundation:
            Uses CUDA FFT decomposition: a(x) = Σ A_k e^(ik·x)
            where A_k are the mode amplitudes and k are wave vectors.

        Args:
            field (np.ndarray): Input field
            threshold (float): Threshold for dominant mode detection

        Returns:
            Dict: Analysis results including:
                - mode_count: Number of dominant modes
                - dominant_frequencies: List of dominant frequencies
                - mode_amplitudes: List of mode amplitudes
                - mode_phases: List of mode phases
                - superposition_quality: Quality metric
        """
        self.logger.info("Analyzing multimode superposition (CUDA)")

        if self.cuda_available:
            # Transfer to GPU
            field_gpu = self.backend.array(field)

            # CUDA FFT
            fft_field_gpu = self.backend.fft(field_gpu)
            power_spectrum_gpu = cp.abs(fft_field_gpu) ** 2

            # Vectorized dominant mode detection
            max_power_gpu = cp.max(power_spectrum_gpu)
            dominant_mask_gpu = power_spectrum_gpu > (threshold * max_power_gpu)
            dominant_modes_gpu = cp.where(dominant_mask_gpu)

            # Extract mode characteristics
            mode_count = int(len(dominant_modes_gpu[0]))
            dominant_frequencies = self._extract_dominant_frequencies_cuda(
                fft_field_gpu, dominant_mask_gpu
            )
            mode_amplitudes = self._extract_mode_amplitudes_cuda(
                fft_field_gpu, dominant_mask_gpu
            )
            mode_phases = self._extract_mode_phases_cuda(
                fft_field_gpu, dominant_mask_gpu
            )

            # Compute superposition quality
            total_power = float(cp.sum(power_spectrum_gpu))
            dominant_power = float(cp.sum(power_spectrum_gpu[dominant_mask_gpu]))
            superposition_quality = (
                dominant_power / total_power if total_power > 0 else 0.0
            )
        else:
            # CPU fallback
            fft_field = np.fft.fftn(field)
            power_spectrum = np.abs(fft_field) ** 2
            max_power = np.max(power_spectrum)
            dominant_mask = power_spectrum > threshold * max_power
            dominant_modes = np.where(dominant_mask)
            mode_count = len(dominant_modes[0])
            dominant_frequencies = self._extract_dominant_frequencies_cpu(
                fft_field, dominant_mask
            )
            mode_amplitudes = self._extract_mode_amplitudes_cpu(
                fft_field, dominant_mask
            )
            mode_phases = self._extract_mode_phases_cpu(fft_field, dominant_mask)
            total_power = np.sum(power_spectrum)
            dominant_power = np.sum(power_spectrum[dominant_mask])
            superposition_quality = (
                dominant_power / total_power if total_power > 0 else 0.0
            )

        results = {
            "mode_count": mode_count,
            "dominant_frequencies": dominant_frequencies,
            "mode_amplitudes": mode_amplitudes,
            "mode_phases": mode_phases,
            "superposition_quality": float(superposition_quality),
            "threshold": threshold,
        }

        self.logger.info(
            f"Superposition analysis completed: {mode_count} dominant modes found"
        )
        return results

    def _extract_dominant_frequencies_cuda(
        self, fft_field: "cp.ndarray", mask: "cp.ndarray"
    ) -> List[float]:
        """Extract dominant frequencies from FFT field on GPU."""
        frequencies = []
        for i in range(len(fft_field.shape)):
            freq_coords = cp.where(mask)[i]
            if len(freq_coords) > 0:
                frequencies.extend(cp.asnumpy(freq_coords).tolist())
        return frequencies

    def _extract_dominant_frequencies_cpu(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract dominant frequencies from FFT field on CPU."""
        frequencies = []
        for i in range(len(fft_field.shape)):
            freq_coords = np.where(mask)[i]
            if len(freq_coords) > 0:
                frequencies.extend(freq_coords.tolist())
        return frequencies

    def _extract_mode_amplitudes_cuda(
        self, fft_field: "cp.ndarray", mask: "cp.ndarray"
    ) -> List[float]:
        """Extract mode amplitudes from FFT field on GPU."""
        amplitudes = cp.abs(fft_field[mask])
        return cp.asnumpy(amplitudes).tolist()

    def _extract_mode_amplitudes_cpu(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract mode amplitudes from FFT field on CPU."""
        amplitudes = np.abs(fft_field[mask])
        return amplitudes.tolist()

    def _extract_mode_phases_cuda(
        self, fft_field: "cp.ndarray", mask: "cp.ndarray"
    ) -> List[float]:
        """Extract mode phases from FFT field on GPU."""
        phases = cp.angle(fft_field[mask])
        return cp.asnumpy(phases).tolist()

    def _extract_mode_phases_cpu(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract mode phases from FFT field on CPU."""
        phases = np.angle(fft_field[mask])
        return phases.tolist()
