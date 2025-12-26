"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power spectrum computation for unified spectral operations.

This module provides power spectrum computation methods that can be used
by UnifiedSpectralOperations, including both single-field and batched processing.
"""

from typing import Dict, Any, Optional, Iterator, Tuple
import numpy as np

from .wave_vectors import get_wave_vectors


def compute_power_spectrum_single(
    field: np.ndarray,
    domain_shape: Tuple[int, ...],
    bins: int = 128,
) -> Dict[str, np.ndarray]:
    """
    Compute power spectrum for a single field.
    
    Physical Meaning:
        Computes isotropic power spectrum P(k) via FFT and radial binning
        for a single field.
        
    Mathematical Foundation:
        Power spectrum: P(k) = |FFT(field)|²
        Radial binning: P(k) → P(|k|) with binning for isotropic spectrum.
        
    Args:
        field (np.ndarray): Input field for power spectrum computation.
        domain_shape (Tuple[int, ...]): Domain shape for wave vector calculation.
        bins (int): Number of bins for radial averaging (default: 128).
            
    Returns:
        Dict[str, np.ndarray]: Dictionary with keys:
            - 'k': Bin centers (wave number magnitudes)
            - 'P': Power spectrum values
    """
    # Compute FFT
    field_spectral = np.fft.fftn(field, norm="ortho")
    power = np.abs(field_spectral) ** 2
    
    # Compute radial binning
    return _radial_bin_power_spectrum(power, domain_shape, bins)


def _radial_bin_power_spectrum(
    power: np.ndarray,
    domain_shape: Tuple[int, ...],
    bins: int,
) -> Dict[str, np.ndarray]:
    """
    Compute radial binning of power spectrum.
    
    Physical Meaning:
        Bins power spectrum P(k) by wave number magnitude |k| for isotropic
        power spectrum computation.
        
    Args:
        power (np.ndarray): Power spectrum |F(k)|².
        domain_shape (Tuple[int, ...]): Domain shape for wave vector calculation.
        bins (int): Number of bins for radial averaging.
        
    Returns:
        Dict[str, np.ndarray]: Dictionary with 'k' (bin centers) and 'P' (values).
    """
    k_vectors = get_wave_vectors(domain_shape)
    
    # Build k-grid for spatial dimensions (first 3)
    if len(domain_shape) >= 3:
        kx, ky, kz = k_vectors[0], k_vectors[1], k_vectors[2]
        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)
        
        # Extract spatial slice if power is 7D
        if power.ndim == 7:
            power_3d = power[:, :, :, 0, 0, 0, 0]
        elif power.ndim == 3:
            power_3d = power
        else:
            power_3d = power.reshape(domain_shape[:3])
            k_magnitude = k_magnitude.reshape(domain_shape[:3])
    else:
        k_magnitude = np.abs(k_vectors[0])
        power_3d = power.flatten()
        k_magnitude = k_magnitude.flatten()
    
    # Bin by |k|
    k_flat = k_magnitude.ravel()
    p_flat = power_3d.ravel()
    
    k_max = float(np.max(k_flat))
    nbins = min(bins, max(32, int(np.cbrt(power_3d.size))))
    bin_edges = np.linspace(0.0, k_max, nbins + 1)
    
    digitized = np.digitize(k_flat, bin_edges) - 1
    digitized = np.clip(digitized, 0, nbins - 1)
    
    Pk = np.zeros(nbins, dtype=power.dtype)
    counts = np.zeros(nbins, dtype=np.int32)
    
    for i in range(nbins):
        mask = digitized == i
        if np.any(mask):
            Pk[i] = np.mean(p_flat[mask])
            counts[i] = np.sum(mask)
    
    k_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    
    nonzero = counts > 0
    Pk = Pk[nonzero]
    k_centers = k_centers[nonzero]
    
    return {"k": k_centers, "P": Pk}

