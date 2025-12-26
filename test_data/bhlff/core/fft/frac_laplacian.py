"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Fractional Laplacian (-Δ)^β implementation in 7D spectral form.

Brief description of the module's purpose and its role in the 7D phase field theory.

Detailed description of the module's functionality, including:
- Physical meaning and theoretical background
- Spectral coefficients construction |k|^(2β)
- Optional CUDA acceleration
- Usage examples and typical workflows

Theoretical Background:
    In spectral space, (-Δ)^β f → |k|^(2β) f̂(k) with |k|² = |k_x|² + |k_φ|² + k_t².

Example:
    >>> op = FractionalLaplacian7D(domain, beta=1.0, use_cuda=True)
    >>> coeffs = op.get_spectral_coefficients()
"""

from typing import Any
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore


class FractionalLaplacian7D:
    """
    7D fractional Laplacian utility for spectral coefficients and application.

    Physical Meaning:
        Represents the non-local operator controlling interactions in the 7D phase
        field. In spectral space, multiplication by |k|^(2β).
    """

    def __init__(self, domain: "Domain", beta: float, use_cuda: bool = True) -> None:
        self.domain = domain
        self.beta = float(beta)
        self.use_cuda = bool(use_cuda) and CUDA_AVAILABLE
        self._xp = cp if self.use_cuda else np
        self._coeffs = None
        self._build_coefficients()

    def apply(self, field: np.ndarray) -> Any:
        """
        Apply (-Δ)^β via FFT: F^{-1}(|k|^(2β) F(field)).

        Physical Meaning:
            Applies the fractional diffusion operator in spectral space.

        Returns:
            Same-shape array: result of applying (-Δ)^β to field.
        """
        xp = self._xp
        f = xp.asarray(field) if self.use_cuda else field
        f_hat = xp.fft.fftn(f, norm="ortho")
        g_hat = f_hat * self._coeffs
        g = xp.fft.ifftn(g_hat, norm="ortho")
        return cp.asnumpy(g) if self.use_cuda else g

    def get_spectral_coefficients(self) -> np.ndarray:
        """Return |k|^(2β) coefficients as CPU array."""
        return cp.asnumpy(self._coeffs) if self.use_cuda else self._coeffs  # type: ignore

    # Internal helpers
    def _build_coefficients(self) -> None:
        xp = self._xp
        N = self.domain.N
        Np = self.domain.N_phi
        Nt = self.domain.N_t

        kx = xp.fft.fftfreq(N)
        ky = xp.fft.fftfreq(N)
        kz = xp.fft.fftfreq(N)
        kphi1 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kphi2 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kphi3 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kt = xp.fft.fftfreq(Nt)

        KX, KY, KZ = xp.meshgrid(kx, ky, kz, indexing="ij")
        P1, P2, P3 = xp.meshgrid(kphi1, kphi2, kphi3, indexing="ij")

        KX7 = KX[:, :, :, None, None, None, None]
        KY7 = KY[:, :, :, None, None, None, None]
        KZ7 = KZ[:, :, :, None, None, None, None]
        P17 = P1[None, None, None, :, None, None, None]
        P27 = P2[None, None, None, None, :, None, None]
        P37 = P3[None, None, None, None, None, :, None]
        KT7 = kt[None, None, None, None, None, None, :]

        k2 = (
            KX7 * KX7
            + KY7 * KY7
            + KZ7 * KZ7
            + P17 * P17
            + P27 * P27
            + P37 * P37
            + KT7 * KT7
        )
        self._coeffs = xp.power(k2 + 0.0, self.beta).astype(xp.float64)


"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Fractional Laplacian (-Δ)^β implementation for 7D space-time in BHLFF.

Physical Meaning:
    Represents the non-local diffusion operator controlling the spread of the
    phase field across spatial and phase coordinates with fractional order β.

Example:
    op = FractionalLaplacian7D(domain, beta=1.0, use_cuda=True)
    coeffs = op.get_spectral_coefficients()
"""

from typing import Any
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore


class FractionalLaplacian7D:
    """
    Fractional Laplacian (-Δ)^β in 7D spectral representation.

    Mathematical Foundation:
        In spectral space, (-Δ)^β f → |k|^(2β) f̂(k), where |k|² is the sum of
        squares of all 7D wave vector components.
    """

    def __init__(self, domain: "Domain", beta: float, use_cuda: bool = True):
        """
        Initialize fractional Laplacian operator.

        Args:
            domain (Domain): 7D domain object with N, N_phi, N_t
            beta (float): fractional order β ∈ (0, 2)
            use_cuda (bool): use CuPy if available
        """
        self.domain = domain
        self.beta = float(beta)
        self.use_cuda = bool(use_cuda) and CUDA_AVAILABLE
        self._xp = cp if self.use_cuda else np
        self._coeffs = None  # type: ignore
        self._build_coefficients()

    def get_spectral_coefficients(self) -> np.ndarray:
        """Return |k|^(2β) as float64 ndarray (CPU)."""
        return cp.asnumpy(self._coeffs) if self.use_cuda else self._coeffs  # type: ignore

    # Internal helpers
    def _build_coefficients(self) -> None:
        xp = self._xp
        N = self.domain.N
        Np = self.domain.N_phi
        Nt = self.domain.N_t

        kx = xp.fft.fftfreq(N)
        ky = xp.fft.fftfreq(N)
        kz = xp.fft.fftfreq(N)
        p = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kt = xp.fft.fftfreq(Nt)

        KX, KY, KZ = xp.meshgrid(kx, ky, kz, indexing="ij")
        P1, P2, P3 = xp.meshgrid(p, p, p, indexing="ij")
        KX7 = KX[:, :, :, None, None, None, None]
        KY7 = KY[:, :, :, None, None, None, None]
        KZ7 = KZ[:, :, :, None, None, None, None]
        P17 = P1[None, None, None, :, None, None, None]
        P27 = P2[None, None, None, None, :, None, None]
        P37 = P3[None, None, None, None, None, :, None]
        KT7 = kt[None, None, None, None, None, None, :]

        k2 = (
            KX7 * KX7
            + KY7 * KY7
            + KZ7 * KZ7
            + P17 * P17
            + P27 * P27
            + P37 * P37
            + KT7 * KT7
        )
        coeffs = xp.power(k2 + 0.0, self.beta)  # (|k|^2)^β
        self._coeffs = coeffs.astype(xp.float64)


"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Fractional Laplacian (-Δ)^β implementation in 7D spectral form.

Physical Meaning:
    Represents the non-local operator controlling interactions in the 7D phase
    field. In spectral space, multiplication by |k|^(2β).
"""

from typing import Any
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore


class FractionalLaplacian7D:
    """7D fractional Laplacian utility for spectral coefficients and application."""

    def __init__(self, domain: "Domain", beta: float, use_cuda: bool = True) -> None:
        self.domain = domain
        self.beta = float(beta)
        self.use_cuda = bool(use_cuda) and CUDA_AVAILABLE
        self._xp = cp if self.use_cuda else np
        self._coeffs = None
        self._build_coefficients()

    def apply(self, field: np.ndarray) -> Any:
        """Apply (-Δ)^β via FFT: F^{-1}(|k|^(2β) F(field))."""
        xp = self._xp
        f = xp.asarray(field) if self.use_cuda else field
        f_hat = xp.fft.fftn(f, norm="ortho")
        g_hat = f_hat * self._coeffs
        g = xp.fft.ifftn(g_hat, norm="ortho")
        return cp.asnumpy(g) if self.use_cuda else g

    def get_spectral_coefficients(self) -> np.ndarray:
        """Return |k|^(2β) coefficients as CPU array."""
        return cp.asnumpy(self._coeffs) if self.use_cuda else self._coeffs  # type: ignore

    def _build_coefficients(self) -> None:
        xp = self._xp
        N = self.domain.N
        Np = self.domain.N_phi
        Nt = self.domain.N_t

        kx = xp.fft.fftfreq(N)
        ky = xp.fft.fftfreq(N)
        kz = xp.fft.fftfreq(N)
        kphi1 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kphi2 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kphi3 = xp.fft.fftfreq(Np) * (2 * xp.pi)
        kt = xp.fft.fftfreq(Nt)

        KX, KY, KZ = xp.meshgrid(kx, ky, kz, indexing="ij")
        P1, P2, P3 = xp.meshgrid(kphi1, kphi2, kphi3, indexing="ij")
        KT = kt

        KX7 = KX[:, :, :, None, None, None, None]
        KY7 = KY[:, :, :, None, None, None, None]
        KZ7 = KZ[:, :, :, None, None, None, None]
        P17 = P1[None, None, None, :, None, None, None]
        P27 = P2[None, None, None, None, :, None, None]
        P37 = P3[None, None, None, None, None, :, None]
        KT7 = KT[None, None, None, None, None, None, :]

        k2 = (
            KX7 * KX7
            + KY7 * KY7
            + KZ7 * KZ7
            + P17 * P17
            + P27 * P27
            + P37 * P37
            + KT7 * KT7
        )
        self._coeffs = xp.power(k2 + 0.0, self.beta).astype(xp.float64)
