"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized gravitational effects (VBP envelope) for Level G.

This module computes envelope-based gravitational descriptors on GPU:
effective metric, curvature invariants, anisotropy index, and focusing
rate. It uses vectorized CuPy operations and optional block processing
for large 3D/ND phase fields.

Physical Meaning:
    Gravity emerges from the curvature of the VBP envelope in 7D phase
    field theory. We compute descriptors derived from phase gradients
    and envelope invariants to characterize effective geometry g_eff[Θ].
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast
import numpy as np

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend
from bhlff.core.domain.cuda_block_processor import (
    CUDABlockProcessor,
)


class GravitationalEffectsCUDA:
    """
    GPU-accelerated VBP envelope gravitational effects calculator.
    """

    def __init__(
        self, domain: Any, params: Dict[str, Any], use_cuda: bool = True
    ) -> None:
        self.domain = domain
        self.params = params
        self.backend = get_optimal_backend()
        self.cuda_available = (
            use_cuda and isinstance(self.backend, CUDABackend)
        )
        self.block_processor: Optional[CUDABlockProcessor] = (
            CUDABlockProcessor(domain) if self.cuda_available else None
        )

        # Parameters for effective metric
        self.c_phi = float(params.get("c_phi", 1.0))
        self.chi_kappa = float(params.get("chi_kappa", 1.0))

    def analyze(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Compute effective metric and envelope curvature descriptors.
        """
        if self.cuda_available:
            return self._analyze_cuda(phase_field)
        return self._analyze_cpu(phase_field)

    # ----------------- CPU path (NumPy) -----------------
    def _analyze_cpu(self, field: np.ndarray) -> Dict[str, Any]:
        grads = self._gradients_cpu(field)
        g_eff = self._effective_metric_cpu(field)
        invariants = self._invariants_cpu(grads)
        anis = self._anisotropy_cpu(g_eff)
        focus = self._focusing_cpu(grads)
        return {
            "effective_metric": g_eff,
            "curvature_invariants": invariants,
            "anisotropy_index": anis,
            "focusing_rate": focus,
        }

    def _gradients_cpu(self, field: np.ndarray) -> Dict[str, np.ndarray]:
        axes = tuple(range(min(3, field.ndim)))
        spatial = np.gradient(field, axis=axes)
        return {"spatial": spatial}

    def _effective_metric_cpu(self, field: np.ndarray) -> np.ndarray:
        """
        Construct effective metric g_eff[Θ] using spatial gradient covariance.

        Physical Meaning:
            Spatial components encode envelope stiffness via gradient
            covariance of Θ. We normalize covariance to keep it
            dimensionless and SPD, then modulate baseline χ/κ.
        """
        # Time component
        g = np.zeros((7, 7))
        g[0, 0] = -1.0 / (self.c_phi**2)

        # Spatial 3x3 block from gradient covariance (SPD, normalized)
        cov = self._compute_spatial_covariance(field)
        anisotropy_gain = float(self.params.get("anisotropy_gain", 0.2))
        A3 = self.chi_kappa * (np.eye(3) + anisotropy_gain * cov)

        # Embed spatial block
        g[1:4, 1:4] = A3

        # Phase coordinates metric (unit baseline scaled by amplitude factor)
        amp = float(np.sqrt(np.mean(np.abs(field) ** 2)) + 1e-15)
        phase_scale = float(self.params.get("phase_metric_scale", 1.0))
        for a in range(4, 7):
            g[a, a] = phase_scale * (1.0 + 0.05 * amp)

        return cast(np.ndarray, g)

    def _compute_spatial_covariance(self, field: np.ndarray) -> np.ndarray:
        """
        Compute normalized 3x3 covariance of spatial gradients (SPD, unitless).
        """
        gx, gy, gz = np.gradient(field, axis=(0, 1, 2))
        # Energy densities and cross-terms
        gxx = float(np.mean(np.real(gx * np.conjugate(gx))))
        gyy = float(np.mean(np.real(gy * np.conjugate(gy))))
        gzz = float(np.mean(np.real(gz * np.conjugate(gz))))
        gxy = float(np.mean(np.real(gx * np.conjugate(gy))))
        gxz = float(np.mean(np.real(gx * np.conjugate(gz))))
        gyz = float(np.mean(np.real(gy * np.conjugate(gz))))

        C = np.array(
            [[gxx, gxy, gxz], [gxy, gyy, gyz], [gxz, gyz, gzz]],
            dtype=float,
        )

        # Normalize to avoid scale dependence and ensure numerical stability
        trace = float(np.trace(C))
        if trace > 1e-30:
            C /= trace

        # Project to nearest SPD via eigenvalue clipping
        evals, evecs = np.linalg.eigh(C)
        evals = np.clip(evals, 0.0, None)
        C_spd = (evecs * evals) @ evecs.T
        return C_spd

    def _invariants_cpu(
        self, grads: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """Compute invariants from gradient covariance.

        scalar = Tr(C);
        spatial_invariant = ||C||_F^2;
        phase_invariant = 0.
        """
        gx, gy, gz = grads["spatial"]
        gxx = float(np.mean(np.real(gx * np.conjugate(gx))))
        gyy = float(np.mean(np.real(gy * np.conjugate(gy))))
        gzz = float(np.mean(np.real(gz * np.conjugate(gz))))
        gxy = float(np.mean(np.real(gx * np.conjugate(gy))))
        gxz = float(np.mean(np.real(gx * np.conjugate(gz))))
        gyz = float(np.mean(np.real(gy * np.conjugate(gz))))

        C = np.array(
            [[gxx, gxy, gxz], [gxy, gyy, gyz], [gxz, gyz, gzz]],
            dtype=float,
        )
        scalar = float(np.trace(C))
        spatial_energy = float(np.sum(C * C))

        return {
            "scalar": scalar,
            "spatial_invariant": spatial_energy,
            "phase_invariant": 0.0,
        }

    def _anisotropy_cpu(self, g: np.ndarray) -> float:
        vals = np.array([g[i, i] for i in range(1, 4)], dtype=float)
        m = float(np.mean(vals))
        return float(np.std(vals) / m) if m > 0 else 0.0

    def _focusing_cpu(self, grads: Dict[str, np.ndarray]) -> float:
        spatial = grads["spatial"]
        focus = 0.0
        for i, gi in enumerate(spatial):
            mag = np.sqrt(np.sum(gi**2))
            if mag > 1e-12:
                n = gi / mag
                div_val = float(np.sum(np.gradient(n, axis=i)))
                focus -= div_val
        return focus

    # ----------------- CUDA path (CuPy) -----------------
    def _analyze_cuda(self, field: np.ndarray) -> Dict[str, Any]:
        cp = self._cp()
        backend = self.backend
        field_gpu = backend.array(field)

        if self.block_processor is None:
            return self._analyze_whole_gpu(field_gpu)

        # Block-based gradient + aggregate descriptors
        spatial_energy = 0.0
        focusing_acc = 0.0
        count_blocks = 0

        for block_gpu, _ in self.block_processor.iterate_blocks_cuda():
            grads = self._gradients_gpu(block_gpu)
            spatial_energy += float(
                cp.sum(cp.stack([cp.sum(cp.abs(g) ** 2) for g in grads]))
            )

            # focusing (approximate per-block)
            focus_block = 0.0
            for i, gi in enumerate(grads):
                mag = cp.sqrt(cp.sum(gi**2))
                if float(mag.get()) > 1e-12:
                    n = gi / mag
                    div = cp.sum(self._gradient_component(n, axis=i))
                    focus_block -= float(div.get())
            focusing_acc += focus_block
            count_blocks += 1

        spatial_invariant = spatial_energy
        g_eff = self._effective_metric_gpu(field_gpu)
        anis = self._anisotropy_gpu(g_eff)
        focusing = focusing_acc / max(1, count_blocks)

        return {
            "effective_metric": self.backend.to_numpy(g_eff),
            "curvature_invariants": {
                "scalar": spatial_invariant,
                "spatial_invariant": spatial_invariant,
                "phase_invariant": 0.0,
            },
            "anisotropy_index": anis,
            "focusing_rate": focusing,
        }

    def _analyze_whole_gpu(self, field_gpu: Any) -> Dict[str, Any]:
        cp = self._cp()
        grads = self._gradients_gpu(field_gpu)
        grad_energy = [cp.sum(cp.abs(g) ** 2) for g in grads]
        spatial_invariant = float(
            cp.sum(cp.stack(grad_energy)).get()
        )
        g_eff = self._effective_metric_gpu(field_gpu)
        anis = self._anisotropy_gpu(g_eff)

        focus = 0.0
        for i, gi in enumerate(grads):
            mag = cp.sqrt(cp.sum(gi**2))
            if float(mag.get()) > 1e-12:
                n = gi / mag
                div = cp.sum(self._gradient_component(n, axis=i))
                focus -= float(div.get())

        return {
            "effective_metric": self.backend.to_numpy(g_eff),
            "curvature_invariants": {
                "scalar": spatial_invariant,
                "spatial_invariant": spatial_invariant,
                "phase_invariant": 0.0,
            },
            "anisotropy_index": anis,
            "focusing_rate": focus,
        }

    def _gradients_gpu(self, field_gpu: Any) -> list[Any]:
        cp = self._cp()
        # Forward difference via roll (periodic by domain default)
        grads = []
        for axis in range(min(3, field_gpu.ndim)):
            grads.append(cp.roll(field_gpu, -1, axis=axis) - field_gpu)
        return grads

    def _gradient_component(self, arr: Any, axis: int) -> Any:
        cp = self._cp()
        return cp.roll(arr, -1, axis=axis) - arr

    def _effective_metric_gpu(self, field_gpu: Any) -> np.ndarray:
        cp = self._cp()
        g = cp.zeros((7, 7), dtype=cp.float64)
        g[0, 0] = -1.0 / (self.c_phi**2)
        for i in range(1, 4):
            g[i, i] = self.chi_kappa
        for a in range(4, 7):
            g[a, a] = 1.0
        amp = float(cp.mean(cp.abs(field_gpu)).get())
        g *= 1.0 + 0.1 * amp
        return cast(np.ndarray, self.backend.to_numpy(g))

    def _anisotropy_gpu(self, g_cpu: np.ndarray) -> float:
        vals = np.array([g_cpu[i, i] for i in range(1, 4)], dtype=float)
        m = float(np.mean(vals))
        return float(np.std(vals) / m) if m > 0 else 0.0

    def _cp(self) -> Any:  # lazy import
        import cupy as cp

        return cp
