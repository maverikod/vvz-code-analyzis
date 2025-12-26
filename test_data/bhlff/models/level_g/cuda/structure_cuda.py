"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized large-scale structure analysis for Level G.

This module provides GPU-accelerated computations for power spectrum
and correlation function analysis on large 3D cosmological fields.
It uses vectorized FFTs and, when needed, memory-aware block processing
to fit within available GPU memory.

Physical Meaning:
    Analyzes formation of large-scale structure through spectral
    characteristics of the density/phase field, providing key
    observables for cosmological validation.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple, Optional, cast
import numpy as np

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend
from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor


class LargeScaleStructureAnalyzerCUDA:
    """
    GPU-accelerated large-scale structure analyzer.

    Methods:
        compute_power_spectrum(field): Radial-averaged |FFT(field)|^2.
        two_point_correlation(field): Inverse FFT of power spectrum.
    """

    def __init__(self, domain: Any, use_cuda: bool = True) -> None:
        self.domain = domain
        self.backend = get_optimal_backend()
        self.cuda_available = (
            use_cuda and isinstance(self.backend, CUDABackend)
        )
        self.block_processor: Optional[CUDABlockProcessor] = (
            CUDABlockProcessor(domain) if self.cuda_available else None
        )

    def compute_power_spectrum(
        self, field: np.ndarray, bins: int = 128
    ) -> Dict[str, Any]:
        """
        Compute isotropic power spectrum P(k) via FFT and radial binning.

        Returns:
            dict with 'k' (bin centers) and 'P' (power spectrum values).
        """
        if self.cuda_available:
            return self._compute_power_spectrum_cuda(field, bins)
        return self._compute_power_spectrum_cpu(field, bins)

    def two_point_correlation(self, field: np.ndarray) -> np.ndarray:
        """
        Compute two-point correlation ξ(r) as IFFT of power spectrum.
        """
        ps = self.compute_power_spectrum(field)
        # Reconstruct approximate isotropic ξ(r) via IFFT of a 3D
        # spectrum approximation built from radial bins
        spectrum_cube = self._reconstruct_spectrum_cube(ps, field.shape)
        corr_any = self.backend.ifft(spectrum_cube)
        corr_np = (
            self.backend.to_numpy(corr_any) if self.cuda_available else corr_any
        )
        return cast(np.ndarray, np.asarray(np.real(corr_np)))

    # ---------------------- CPU path ----------------------
    def _compute_power_spectrum_cpu(
        self, field: np.ndarray, bins: int
    ) -> Dict[str, Any]:
        backend = self.backend
        axes = (0, 1, 2)
        F = backend.fft(field, axes=axes)
        power = np.abs(F) ** 2
        k_mag, Pk = self._radial_bin_cpu(power, field.shape)
        return {"k": k_mag, "P": Pk}

    def _radial_bin_cpu(
        self, power: np.ndarray, shape: Tuple[int, int, int]
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Build k-grid
        Lx, Ly, Lz = self._domain_lengths()
        kx = np.fft.fftfreq(shape[0], d=Lx / shape[0])
        ky = np.fft.fftfreq(shape[1], d=Ly / shape[1])
        kz = np.fft.fftfreq(shape[2], d=Lz / shape[2])
        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k = np.sqrt(KX**2 + KY**2 + KZ**2)

        # Bin by |k|
        k_flat = k.ravel()
        p_flat = power.ravel()
        k_max = float(k_flat.max())
        nbins = min(256, max(32, int(np.cbrt(power.size))))
        bins = np.linspace(0.0, k_max, nbins + 1)
        digitized = np.digitize(k_flat, bins) - 1

        Pk = np.zeros(nbins)
        counts = np.zeros(nbins)
        for i in range(nbins):
            m = digitized == i
            if np.any(m):
                Pk[i] = p_flat[m].mean()
                counts[i] = m.sum()

        # Bin centers
        k_centers = 0.5 * (bins[:-1] + bins[1:])
        # Normalize by counts to avoid bias in sparse shells
        nonzero = counts > 0
        Pk = Pk[nonzero]
        k_centers = k_centers[nonzero]
        return k_centers, Pk

    # ---------------------- CUDA path ---------------------
    def _compute_power_spectrum_cuda(
        self, field: np.ndarray, bins: int
    ) -> Dict[str, Any]:
        backend = self.backend
        field_gpu = backend.array(field)

        try:
            return self._power_spectrum_whole_gpu(field_gpu)
        except Exception:
            # Fallback to block-based accumulation if whole FFT fails
            if self.block_processor is None:
                raise
            return self._power_spectrum_blocks_gpu(field_gpu)

    def _power_spectrum_whole_gpu(self, field_gpu: Any) -> Dict[str, Any]:
        cp = self._cp()
        backend = self.backend
        axes = (0, 1, 2)
        F = backend.fft(field_gpu, axes=axes)
        power = cp.abs(F) ** 2
        k_mag, Pk = self._radial_bin_gpu(power, field_gpu.shape)
        return {
            "k": self.backend.to_numpy(k_mag),
            "P": self.backend.to_numpy(Pk),
        }

    def _power_spectrum_blocks_gpu(self, field_gpu: Any) -> Dict[str, Any]:
        cp = self._cp()
        assert self.block_processor is not None

        # Accumulate partial spectra (simple averaging over blocks)
        spectra = []
        ks = []
        for block_gpu, _ in self.block_processor.iterate_blocks_cuda():
            axes = (0, 1, 2)
            F = cp.fft.fftn(block_gpu, axes=axes)
            power = cp.abs(F) ** 2
            k_mag, Pk = self._radial_bin_gpu(power, block_gpu.shape)
            spectra.append(Pk)
            ks.append(k_mag)

        # Interpolate to common k-grid (use first block grid)
        k0 = ks[0]
        P_acc = cp.zeros_like(spectra[0])
        for k_i, P_i in zip(ks, spectra):
            P_acc += cp.interp(k0, k_i, P_i, left=0.0, right=0.0)
        P_acc /= float(len(spectra))

        return {
            "k": self.backend.to_numpy(k0),
            "P": self.backend.to_numpy(P_acc),
        }

    def _radial_bin_gpu(
        self, power: Any, shape: Tuple[int, int, int]
    ) -> Tuple[Any, Any]:
        cp = self._cp()
        Lx, Ly, Lz = self._domain_lengths()
        kx = cp.fft.fftfreq(shape[0], d=Lx / shape[0])
        ky = cp.fft.fftfreq(shape[1], d=Ly / shape[1])
        kz = cp.fft.fftfreq(shape[2], d=Lz / shape[2])
        KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij")
        k = cp.sqrt(KX**2 + KY**2 + KZ**2)

        k_flat = k.ravel()
        p_flat = power.ravel()
        k_max = float(cp.max(k_flat).get())
        nbins = int(min(256, max(32, np.cbrt(power.size))))
        bins = cp.linspace(0.0, k_max, nbins + 1)
        # digitize on GPU
        idx = cp.searchsorted(bins, k_flat, side="right") - 1
        idx = cp.clip(idx, 0, nbins - 1)

        Pk = cp.zeros(nbins, dtype=cp.float64)
        counts = cp.zeros(nbins, dtype=cp.float64)

        # Use bincount for efficiency
        idx_i = idx.astype(cp.int32)
        weighted = cp.bincount(idx_i, weights=p_flat, minlength=nbins)
        Pk = weighted.astype(cp.float64)
        counts = cp.bincount(idx_i, minlength=nbins).astype(cp.float64)

        # Avoid division by zero
        mask = counts > 0
        Pk = cp.where(mask, Pk / counts, 0.0)

        k_centers = 0.5 * (bins[:-1] + bins[1:])
        return k_centers, Pk

    # ---------------------- helpers ----------------------
    def _domain_lengths(self) -> Tuple[float, float, float]:
        try:
            size = getattr(self.domain, "size", None)
            if size is not None:
                Lx, Ly, Lz = size
                return float(Lx), float(Ly), float(Lz)
        except Exception:
            return 1.0, 1.0, 1.0
        return 1.0, 1.0, 1.0

    def _reconstruct_spectrum_cube(
        self, ps: Dict[str, np.ndarray], shape: Tuple[int, ...]
    ) -> np.ndarray:
        # Build isotropic spectrum cube from radial P(k) by interpolation
        k_vec = ps["k"]
        P_vec = ps["P"]
        Lx, Ly, Lz = self._domain_lengths()
        kx = np.fft.fftfreq(shape[0], d=Lx / shape[0])
        ky = np.fft.fftfreq(shape[1], d=Ly / shape[1])
        kz = np.fft.fftfreq(shape[2], d=Lz / shape[2])
        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        kmag = np.sqrt(KX**2 + KY**2 + KZ**2)
        P_iso = np.interp(kmag.ravel(), k_vec, P_vec, left=0.0, right=0.0)
        return P_iso.reshape(shape)

    def _cp(self) -> Any:  # lazy import
        import cupy as cp

        return cp
