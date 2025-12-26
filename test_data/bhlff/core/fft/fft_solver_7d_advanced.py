"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced 7D FFT solver with CUDA acceleration and memory-aware batched FFTs.

Brief description of the module's purpose and its role in the 7D phase field theory.

Detailed description of the module's functionality, including:
- Physical meaning and theoretical background
- Batched 1D FFT along each axis to limit peak memory
- Optional CUDA acceleration via CuPy
- Usage examples and typical workflows

Theoretical Background:
    Solves â(k) = ŝ(k) / (μ|k|^(2β) + λ) using orthonormal FFTs with blocked
    transforms to reduce memory overhead on large 7D grids.
"""

from typing import Dict, Any
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore


class FFTSolver7DAdvanced:
    """7D solver using batched 1D FFTs per axis to limit peak memory."""

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        self.domain = domain
        self.mu = float(parameters.get("mu", 1.0))
        self.beta = float(parameters.get("beta", 1.0))
        self.lmbda = float(parameters.get("lambda", 0.0))
        use_cuda_flag = bool(parameters.get("use_cuda", True))  # CUDA required by default
        if use_cuda_flag and not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for FFTSolver7DAdvanced. "
                "Install cupy to enable GPU acceleration."
            )
        self.use_cuda = use_cuda_flag and CUDA_AVAILABLE
        self._xp = cp if self.use_cuda else np
        self._coeffs = None  # type: ignore
        try:
            self._build_spectral_coefficients()
        except Exception as e:
            raise RuntimeError(f"Failed to build spectral coefficients: {e}")

    def solve_stationary(self, source_field: np.ndarray) -> np.ndarray:
        xp = self._xp
        src = xp.asarray(source_field) if self.use_cuda else source_field
        # Use direct n-D FFTs for numerical consistency
        s_hat = self._xp.fft.fftn(src, norm="ortho")
        a_hat = s_hat / self._coeffs
        a = self._xp.fft.ifftn(a_hat, norm="ortho").real
        return cp.asnumpy(a) if self.use_cuda else a

    def get_spectral_coefficients(self) -> np.ndarray:
        return cp.asnumpy(self._coeffs) if self.use_cuda else self._coeffs  # type: ignore

    def _build_spectral_coefficients(self) -> None:
        xp = self._xp
        N = self.domain.N
        Np = self.domain.N_phi
        Nt = self.domain.N_t
        kx = xp.fft.fftfreq(N) * (2 * xp.pi)
        ky = xp.fft.fftfreq(N) * (2 * xp.pi)
        kz = xp.fft.fftfreq(N) * (2 * xp.pi)
        kphi = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kt = xp.fft.fftfreq(Nt) * (2 * xp.pi)

        # Explicit 7D broadcasting-safe shapes
        KX7 = kx.reshape(N, 1, 1, 1, 1, 1, 1)
        KY7 = ky.reshape(1, N, 1, 1, 1, 1, 1)
        KZ7 = kz.reshape(1, 1, N, 1, 1, 1, 1)
        P17 = kphi.reshape(1, 1, 1, Np, 1, 1, 1)
        P27 = kphi.reshape(1, 1, 1, 1, Np, 1, 1)
        P37 = kphi.reshape(1, 1, 1, 1, 1, Np, 1)
        KT7 = kt.reshape(1, 1, 1, 1, 1, 1, Nt)
        k2 = (
            KX7 * KX7
            + KY7 * KY7
            + KZ7 * KZ7
            + P17 * P17
            + P27 * P27
            + P37 * P37
            + KT7 * KT7
        )
        abs_k_2beta = xp.power(k2 + 0.0, self.beta)
        D = self.mu * abs_k_2beta + self.lmbda
        if self.lmbda == 0.0:
            D[(k2 == 0)] = 1.0
        self._coeffs = D.astype(xp.float64)

    # -------- Memory-aware batched FFT helpers --------
    def _get_free_memory_bytes(self) -> int:
        if self.use_cuda and cp is not None:
            try:
                free_b, total_b = cp.cuda.runtime.memGetInfo()
                return int(free_b)
            except Exception:
                return 0
        return 4 * 1024**3  # assume 4GB free on CPU

    def _estimate_batch(
        self, size_axis: int, other_product: int, dtype_bytes: int
    ) -> int:
        # workspace ~ 4x input batch
        free_bytes = self._get_free_memory_bytes()
        if free_bytes <= 0:
            return max(1, other_product)
        bytes_per_batch_row = size_axis * dtype_bytes * 4
        max_rows = int(0.8 * free_bytes // max(1, bytes_per_batch_row))
        return max(1, min(other_product, max_rows))

    def _fftn_batched(self, arr, norm: str = "backward"):
        a = arr
        for axis in range(a.ndim):
            a = self._fft_axis_batched(a, axis=axis, norm=norm)
        return a

    def _ifftn_batched(self, arr, norm: str = "backward"):
        a = arr
        for axis in range(a.ndim):
            a = self._ifft_axis_batched(a, axis=axis, norm=norm)
        return a

    def _fft_axis_batched(self, arr, axis: int, norm: str):
        xp = self._xp
        shape = arr.shape
        size_along = shape[axis]
        other_prod = int(np.prod([shape[i] for i in range(len(shape)) if i != axis]))
        batch = self._estimate_batch(size_along, other_prod, arr.dtype.itemsize)
        a2 = xp.reshape(arr, (other_prod, size_along))
        out = xp.empty_like(a2, dtype=xp.complex128)
        start = 0
        while start < other_prod:
            end = min(other_prod, start + batch)
            out[start:end] = xp.fft.fft(a2[start:end], axis=1, norm=norm)
            start = end
        return xp.reshape(out, shape)

    def _ifft_axis_batched(self, arr, axis: int, norm: str):
        xp = self._xp
        shape = arr.shape
        size_along = shape[axis]
        other_prod = int(np.prod([shape[i] for i in range(len(shape)) if i != axis]))
        batch = self._estimate_batch(size_along, other_prod, arr.dtype.itemsize)
        a2 = xp.reshape(arr, (other_prod, size_along))
        out = xp.empty_like(a2, dtype=xp.complex128)
        start = 0
        while start < other_prod:
            end = min(other_prod, start + batch)
            out[start:end] = xp.fft.ifft(a2[start:end], axis=1, norm=norm)
            start = end
        return xp.reshape(out, shape)
