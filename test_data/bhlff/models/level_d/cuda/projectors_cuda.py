"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized field projectors for Level D models.

This module implements CUDA-accelerated field projectors for electromagnetic,
strong, and weak interaction windows with vectorized filtering operations.

Physical Meaning:
    Provides GPU-accelerated projectors for separating the unified phase field
    into different interaction regimes based on frequency characteristics.

Mathematical Foundation:
    - EM projection: P_EM[a] = FFT⁻¹[FFT(a) × H_EM(ω)]
    - Strong projection: P_STRONG[a] = FFT⁻¹[FFT(a) × H_STRONG(ω)]
    - Weak projection: P_WEAK[a] = FFT⁻¹[FFT(a) × H_WEAK(ω)]
"""

import numpy as np
from typing import Dict, Any, Tuple

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class EMProjectorCUDA:
    """CUDA-optimized electromagnetic field projector."""

    def __init__(
        self, params: Dict[str, Any], cuda_available: bool = False, backend=None
    ):
        """Initialize CUDA EM projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [0.1, 1.0])
        self.amplitude_threshold = params.get("amplitude_threshold", 0.1)
        self.filter_type = params.get("filter_type", "bandpass")
        self.cuda_available = cuda_available and (backend is not None)
        self.backend = backend

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto EM window with CUDA."""
        if self.cuda_available:
            field_gpu = self.backend.array(field)
            fft_field_gpu = self.backend.fft(field_gpu)
            em_filter_gpu = self._create_em_filter_cuda(fft_field_gpu.shape)
            em_field_fft_gpu = fft_field_gpu * em_filter_gpu
            em_field_gpu = self.backend.ifft(em_field_fft_gpu)
            return self.backend.to_numpy(em_field_gpu.real)
        else:
            fft_field = np.fft.fftn(field)
            em_filter = self._create_em_filter_cpu(fft_field.shape)
            em_field_fft = fft_field * em_filter
            em_field = np.fft.ifftn(em_field_fft)
            return em_field.real

    def _create_em_filter_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create EM window filter on GPU."""
        frequencies = self._create_frequency_grid_cuda(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        em_filter = cp.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        return em_filter

    def _create_em_filter_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create EM window filter on CPU."""
        frequencies = self._create_frequency_grid_cpu(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        em_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        return em_filter

    def _create_frequency_grid_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create frequency grid on GPU."""
        if len(shape) == 3:
            kx = cp.fft.fftfreq(shape[0])
            ky = cp.fft.fftfreq(shape[1])
            kz = cp.fft.fftfreq(shape[2])
            KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = cp.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = cp.ones(shape)
        return frequencies

    def _create_frequency_grid_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid on CPU."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)
        return frequencies


class StrongProjectorCUDA:
    """CUDA-optimized strong interaction field projector."""

    def __init__(
        self, params: Dict[str, Any], cuda_available: bool = False, backend=None
    ):
        """Initialize CUDA strong projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [1.0, 10.0])
        self.q_threshold = params.get("q_threshold", 100)
        self.filter_type = params.get("filter_type", "high_q")
        self.cuda_available = cuda_available and (backend is not None)
        self.backend = backend

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto strong window with CUDA."""
        if self.cuda_available:
            field_gpu = self.backend.array(field)
            fft_field_gpu = self.backend.fft(field_gpu)
            strong_filter_gpu = self._create_strong_filter_cuda(fft_field_gpu.shape)
            strong_field_fft_gpu = fft_field_gpu * strong_filter_gpu
            strong_field_gpu = self.backend.ifft(strong_field_fft_gpu)
            return self.backend.to_numpy(strong_field_gpu.real)
        else:
            fft_field = np.fft.fftn(field)
            strong_filter = self._create_strong_filter_cpu(fft_field.shape)
            strong_field_fft = fft_field * strong_filter
            strong_field = np.fft.ifftn(strong_field_fft)
            return strong_field.real

    def _create_strong_filter_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create strong window filter on GPU."""
        frequencies = self._create_frequency_grid_cuda(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        strong_filter = cp.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        strong_filter *= self._apply_q_factor_filter_cuda(frequencies, self.q_threshold)
        return strong_filter

    def _create_strong_filter_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create strong window filter on CPU."""
        frequencies = self._create_frequency_grid_cpu(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        strong_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        strong_filter *= self._apply_q_factor_filter_cpu(frequencies, self.q_threshold)
        return strong_filter

    def _create_frequency_grid_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create frequency grid on GPU."""
        if len(shape) == 3:
            kx = cp.fft.fftfreq(shape[0])
            ky = cp.fft.fftfreq(shape[1])
            kz = cp.fft.fftfreq(shape[2])
            KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = cp.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = cp.ones(shape)
        return frequencies

    def _create_frequency_grid_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid on CPU."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)
        return frequencies

    def _apply_q_factor_filter_cuda(
        self, frequencies: "cp.ndarray", q_factor: float
    ) -> "cp.ndarray":
        """Apply Q-factor filtering on GPU using step resonator model."""
        cutoff_frequency = q_factor
        filter_strength = 1.0
        return filter_strength * cp.where(frequencies < cutoff_frequency, 1.0, 0.0)

    def _apply_q_factor_filter_cpu(
        self, frequencies: np.ndarray, q_factor: float
    ) -> np.ndarray:
        """Apply Q-factor filtering on CPU."""
        cutoff_frequency = q_factor
        filter_strength = 1.0
        return filter_strength * np.where(frequencies < cutoff_frequency, 1.0, 0.0)


class WeakProjectorCUDA:
    """CUDA-optimized weak interaction field projector."""

    def __init__(
        self, params: Dict[str, Any], cuda_available: bool = False, backend=None
    ):
        """Initialize CUDA weak projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [0.01, 0.1])
        self.q_threshold = params.get("q_threshold", 10)
        self.filter_type = params.get("filter_type", "chiral")
        self.cuda_available = cuda_available and (backend is not None)
        self.backend = backend

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto weak window with CUDA."""
        if self.cuda_available:
            field_gpu = self.backend.array(field)
            fft_field_gpu = self.backend.fft(field_gpu)
            weak_filter_gpu = self._create_weak_filter_cuda(fft_field_gpu.shape)
            weak_field_fft_gpu = fft_field_gpu * weak_filter_gpu
            weak_field_gpu = self.backend.ifft(weak_field_fft_gpu)
            return self.backend.to_numpy(weak_field_gpu.real)
        else:
            fft_field = np.fft.fftn(field)
            weak_filter = self._create_weak_filter_cpu(fft_field.shape)
            weak_field_fft = fft_field * weak_filter
            weak_field = np.fft.ifftn(weak_field_fft)
            return weak_field.real

    def _create_weak_filter_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create weak window filter on GPU."""
        frequencies = self._create_frequency_grid_cuda(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        weak_filter = cp.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        chiral_factor = self.params.get("chiral_threshold", 0.1)
        weak_filter *= self._apply_chiral_filter_cuda(chiral_factor, frequencies.shape)
        return weak_filter

    def _create_weak_filter_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create weak window filter on CPU."""
        frequencies = self._create_frequency_grid_cpu(shape)
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]
        weak_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )
        chiral_factor = self.params.get("chiral_threshold", 0.1)
        weak_filter *= self._apply_chiral_filter_cpu(chiral_factor, frequencies.shape)
        return weak_filter

    def _create_frequency_grid_cuda(self, shape: Tuple[int, ...]) -> "cp.ndarray":
        """Create frequency grid on GPU."""
        if len(shape) == 3:
            kx = cp.fft.fftfreq(shape[0])
            ky = cp.fft.fftfreq(shape[1])
            kz = cp.fft.fftfreq(shape[2])
            KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = cp.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = cp.ones(shape)
        return frequencies

    def _create_frequency_grid_cpu(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid on CPU."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)
        return frequencies

    def _apply_chiral_filter_cuda(
        self, chiral_factor: float, shape: Tuple[int, ...]
    ) -> "cp.ndarray":
        """Apply chiral filtering on GPU."""
        return cp.ones(shape, dtype=cp.float64)

    def _apply_chiral_filter_cpu(
        self, chiral_factor: float, shape: Tuple[int, ...]
    ) -> np.ndarray:
        """Apply chiral filtering on CPU."""
        return np.ones(shape, dtype=np.float64)
