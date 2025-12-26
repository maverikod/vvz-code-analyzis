"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized cosmological evolution for Level G.

This module implements GPU-accelerated phase field evolution for
cosmological models in the 7D phase field theory. It uses vectorized
CuPy operations and memory-aware block processing via CUDABlockProcessor
to evolve large 3D/ND fields efficiently. When CUDA is unavailable, it
falls back to NumPy with identical numerical flow.

Physical Meaning:
    Evolves the phase field configuration with cosmological expansion
    and fractional Laplacian dynamics consistent with the Level G
    specification. The spectral operator corresponds to μ|k|^{2β} + λ.

Mathematical Foundation:
    For a field a(x), we integrate a semi-implicit step of
    ∂a/∂t = -[μ(-Δ)^β a + λ a] with optional Hubble friction. In
    spectral space the update is:
        â_{t+Δt} = â_t / (1 + Δt [ μ|k|^{2β} + λ ])
    which is unconditionally stable and vectorizable.

Example:
    >>> evo = CosmologicalEvolutionCUDA(
    ...     domain, {"mu": 1.0, "beta": 1.0, "lambda": 0.0}
    ... )
    >>> a_next = evo.evolve_step(a_current, t, dt, scale_factor=1.0)
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, cast
import numpy as np

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend
from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor


class CosmologicalEvolutionCUDA:
    """
    CUDA-optimized cosmological phase field evolution.

    Physical Meaning:
        Evolves the phase field using a stable spectral update with
        fractional Laplacian dynamics and optional Hubble friction.
        Uses GPU acceleration with vectorization and block processing
        when available for large cosmological grids.

    Attributes:
        mu (float): Diffusion coefficient.
        beta (float): Fractional order (0<β≤2 typical).
        lambda_param (float): Linear damping parameter.
        hubble_friction (bool): Whether to include 3H∂a/∂t term
            (handled via a multiplicative attenuation per step).
        backend: CUDA or CPU backend with unified API.
        cuda_available (bool): True if running on CUDA.
        block_processor (Optional[CUDABlockProcessor]):
            Processor for GPU blocks.
    """

    def __init__(
        self,
        domain: Any,
        cosmology_params: Dict[str, Any],
        use_cuda: bool = True,
    ) -> None:
        """
        Initialize cosmological evolution operator.

        Args:
            domain: Computational domain.
            cosmology_params: Parameters containing at least μ, β, λ and H0.
            use_cuda: Prefer CUDA when available.
        """
        self.domain = domain
        self.params = cosmology_params
        self.mu = float(cosmology_params.get("mu", 1.0))
        self.beta = float(cosmology_params.get("beta", 1.0))
        self.lambda_param = float(cosmology_params.get("lambda", 0.0))
        self.H0 = float(cosmology_params.get("H0", 70.0))
        self.hubble_friction = bool(
            cosmology_params.get("hubble_friction", True)
        )

        # Backend selection
        self.backend = get_optimal_backend()
        self.cuda_available = (
            use_cuda and isinstance(self.backend, CUDABackend)
        )

        # Optional CUDA block processor (80% GPU memory utilization heuristic)
        self.block_processor: Optional[CUDABlockProcessor]
        self.block_processor = (
            CUDABlockProcessor(domain) if self.cuda_available else None
        )

        # Precompute spectral grids for spatial axes (first 3 dims)
        self._k_grids_cpu: Optional[
            Tuple[np.ndarray, np.ndarray, np.ndarray]
        ] = None

    def evolve_step(
        self, field: np.ndarray, t: float, dt: float, scale_factor: float = 1.0
    ) -> np.ndarray:
        """
        Evolve the field by one time step using a stable spectral update.

        Physical Meaning:
            Applies cosmological damping and fractional Laplacian dynamics
            over Δt, vectorized across the full grid or per-GPU-blocks.

        Args:
            field: Real/complex array of shape domain.shape.
            t: Current cosmological time (unused in constant-coeff step).
            dt: Time step.
            scale_factor: Current expansion factor a(t) (used for friction).

        Returns:
            np.ndarray: Updated field on CPU memory.
        """
        if self.cuda_available:
            return self._evolve_step_cuda(field, dt, scale_factor)
        return self._evolve_step_cpu(field, dt, scale_factor)

    # -------------------------- CPU path ---------------------------
    def _evolve_step_cpu(
        self, field: np.ndarray, dt: float, scale_factor: float
    ) -> np.ndarray:
        backend = self.backend  # CPUBackend
        # FFT over first 3 spatial axes if present
        axes = tuple(range(min(3, field.ndim)))

        kx, ky, kz = self._get_k_grids_cpu(field.shape[:3])
        k2 = kx * kx + ky * ky + kz * kz
        op = (
            self.mu * np.power(k2, self.beta, where=k2 > 0) + self.lambda_param
        )

        # Transform
        a_hat = backend.fft(field, axes=axes)
        # Stable implicit step: divide by (1 + dt * op)
        denom = 1.0 + dt * op[(...,) + (slice(None),) * (field.ndim - 3)]
        a_hat_next = a_hat / denom
        a_next_any = backend.ifft(a_hat_next, axes=axes)
        a_next = np.asarray(a_next_any)

        a_next = np.real(a_next) if np.isrealobj(field) else a_next

        if self.hubble_friction:
            H = self._hubble(scale_factor)
            attenuation = 1.0 / (1.0 + 3.0 * H * dt)
            a_next = a_next * attenuation

        return cast(np.ndarray, a_next).astype(field.dtype, copy=False)

    def _get_k_grids_cpu(
        self, spatial_shape: Tuple[int, int, int]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._k_grids_cpu is not None and all(
            g.shape[0] == s for g, s in zip(self._k_grids_cpu, spatial_shape)
        ):
            KX, KY, KZ = self._k_grids_cpu
            return KX, KY, KZ

        Lx, Ly, Lz = self._get_domain_lengths()
        kx = np.fft.fftfreq(spatial_shape[0], d=Lx / spatial_shape[0])
        ky = np.fft.fftfreq(spatial_shape[1], d=Ly / spatial_shape[1])
        kz = np.fft.fftfreq(spatial_shape[2], d=Lz / spatial_shape[2])
        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        self._k_grids_cpu = (KX, KY, KZ)
        return self._k_grids_cpu

    # -------------------------- CUDA path --------------------------
    def _evolve_step_cuda(
        self, field: np.ndarray, dt: float, scale_factor: float
    ) -> np.ndarray:
        backend = self.backend  # CUDABackend

        field_gpu = backend.array(field)

        if self.block_processor is None:
            # Process as a whole and bring back to CPU
            a_next_gpu = self._evolve_whole_gpu(field_gpu, dt, scale_factor)
            a_cpu = self.backend.to_numpy(a_next_gpu)
            return cast(np.ndarray, a_cpu).astype(field.dtype, copy=False)

        # Block-wise processing to fit memory
        processed_blocks = []
        itr = self.block_processor.iterate_blocks_cuda()
        for block_gpu, block_info in itr:
            updated_block = self._evolve_whole_gpu(block_gpu, dt, scale_factor)
            processed_blocks.append((updated_block, block_info))

        merged = self.block_processor.merge_blocks_cuda(processed_blocks)
        result = backend.to_numpy(merged)
        return cast(np.ndarray, result).astype(field.dtype, copy=False)

    def _evolve_whole_gpu(
        self,
        field_gpu: Any,
        dt: float,
        scale_factor: float,
    ) -> Any:
        cp = self._cp()
        backend = self.backend  # CUDABackend
        axes = tuple(range(min(3, field_gpu.ndim)))

        # Build k-grids on GPU for current shape
        spatial_shape = tuple(int(s) for s in field_gpu.shape[:3])
        Lx, Ly, Lz = self._get_domain_lengths()
        kx = cp.fft.fftfreq(spatial_shape[0], d=Lx / spatial_shape[0])
        ky = cp.fft.fftfreq(spatial_shape[1], d=Ly / spatial_shape[1])
        kz = cp.fft.fftfreq(spatial_shape[2], d=Lz / spatial_shape[2])
        KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij")
        k2 = KX * KX + KY * KY + KZ * KZ
        op = (
            self.mu * cp.power(k2, self.beta, where=k2 > 0) + self.lambda_param
        )

        a_hat = backend.fft(field_gpu, axes=axes)
        denom = 1.0 + dt * op[(...,) + (slice(None),) * (field_gpu.ndim - 3)]
        a_hat_next = a_hat / denom
        a_next = backend.ifft(a_hat_next, axes=axes)

        if self.hubble_friction:
            H = self._hubble(scale_factor)
            attenuation = 1.0 / (1.0 + 3.0 * H * dt)
            a_next = a_next * attenuation

        return a_next

    # -------------------------- helpers ---------------------------
    def _hubble(self, scale_factor: float) -> float:
        # Simple H(a) ~ H0 for short steps; placeholder consistent with spec
        return self.H0

    def _get_domain_lengths(self) -> Tuple[float, float, float]:
        # Attempt to read from domain
        try:
            size = getattr(self.domain, "size", None)
            if size is not None:
                Lx, Ly, Lz = size
                return float(Lx), float(Ly), float(Lz)
        except Exception:
            # Fallback to unit box if not available
            return 1.0, 1.0, 1.0
        return 1.0, 1.0, 1.0

    def _cp(self) -> Any:  # lazy import helper for type checkers
        import cupy as cp

        return cp
