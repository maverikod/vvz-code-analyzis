"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU FFT helpers with physics and ortho normalization.
"""

from typing import Tuple
import numpy as np
import numpy.fft as np_fft
from .volume import compute_volume_element


def forward_fft_cpu(
    field: np.ndarray, normalization: str, domain_shape: Tuple[int, ...]
) -> np.ndarray:
    axes = tuple(range(field.ndim)) if field.ndim > 0 else None
    if normalization == "ortho":
        return np_fft.fftn(field, axes=axes, norm="ortho")
    if normalization == "physics":
        out = np_fft.fftn(field, axes=axes, norm="ortho")
        out *= compute_volume_element(domain_shape)
        return out
    raise ValueError(f"Unsupported normalization type: {normalization}")


def inverse_fft_cpu(
    spectral_field: np.ndarray, normalization: str, domain_shape: Tuple[int, ...]
) -> np.ndarray:
    axes = tuple(range(spectral_field.ndim)) if spectral_field.ndim > 0 else None
    if normalization == "ortho":
        return np_fft.ifftn(spectral_field, axes=axes, norm="ortho")
    if normalization == "physics":
        volume_element = compute_volume_element(domain_shape)
        field_real = np_fft.ifftn(
            spectral_field / volume_element, axes=axes, norm="ortho"
        )
        first = field_real.reshape(-1)[0]
        if np.abs(first) > 0:
            align = np.exp(-1j * np.angle(first))
            field_real = field_real * align
        norm = np.linalg.norm(field_real)
        if norm > 0:
            field_real = field_real / norm
        return field_real
    raise ValueError(f"Unsupported normalization type: {normalization}")
