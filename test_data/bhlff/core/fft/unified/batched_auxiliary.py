"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Batched auxiliary operations for unified spectral operations.

This module provides batched versions of auxiliary operations like power spectrum
computation and preconditioning that can operate on independent channel groups
with CUDA streams for optimal GPU utilization.

Physical Meaning:
    Provides batched processing for auxiliary spectral operations, enabling
    efficient processing of large fields by operating on independent channel
    groups in parallel using CUDA streams.

Mathematical Foundation:
    Batched operations process multiple independent channel groups simultaneously:
    - Power spectrum: P(k) = |FFT(field)|² for each channel group
    - Preconditioning: M⁻¹r for each channel group independently
    - Operations use 80% GPU memory per batch for optimal utilization

Example:
    >>> from bhlff.core.fft.unified.batched_auxiliary import compute_power_spectrum_batched
    >>> batch_iterator = field_array.iter_batches(max_gpu_ratio=0.8)
    >>> power_spectra = compute_power_spectrum_batched(batch_iterator, domain)
"""

from typing import Iterator, Dict, Any, Optional, Tuple
import logging
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ...exceptions import CUDANotAvailableError
from bhlff.utils.cuda_backend import CUDABackend

logger = logging.getLogger(__name__)


def compute_power_spectrum_batched(
    batch_iterator: Iterator[Dict[str, Any]],
    domain: "Domain",
    bins: int = 128,
    gpu_memory_ratio: float = 0.8,
) -> Dict[str, np.ndarray]:
    """
    Compute power spectrum from batched field iterator with CUDA streams.
    
    Physical Meaning:
        Computes isotropic power spectrum P(k) via FFT and radial binning
        for fields processed in batches. Each batch is processed independently
        using CUDA streams for parallel execution.
        
    Mathematical Foundation:
        For each batch:
        - FFT: F(k) = FFT(field_batch)
        - Power: P(k) = |F(k)|²
        - Radial binning: P(k) → P(|k|) with binning
        Results are combined across batches.
        
    Args:
        batch_iterator (Iterator[Dict[str, Any]]): Iterator yielding batches
            with keys:
            - 'batch_id': Unique batch identifier for logging
            - 'data': Field data (np.ndarray or cp.ndarray)
            - 'slices': Slice indices for this batch (optional)
        domain (Domain): Computational domain for wave vector calculation.
        bins (int): Number of bins for radial averaging (default: 128).
        gpu_memory_ratio (float): GPU memory ratio to use per batch (default: 0.8).
            
    Returns:
        Dict[str, np.ndarray]: Dictionary with keys:
            - 'k': Bin centers (wave number magnitudes)
            - 'P': Power spectrum values (averaged across batches)
            
    Raises:
        CUDANotAvailableError: If CUDA is not available (required for batched ops).
    """
    CUDABackend.require_cuda()
    
    if not CUDA_AVAILABLE:
        raise CUDANotAvailableError(
            "CUDA is required for batched power spectrum computation. "
            "CPU fallback is NOT ALLOWED. "
            "Please install CuPy and ensure CUDA is properly configured."
        )
    
    logger.info(
        f"Starting batched power spectrum computation with "
        f"gpu_memory_ratio={gpu_memory_ratio:.1%}, bins={bins}"
    )
    
    # Collect power spectra from all batches
    all_k_centers = []
    all_Pk_values = []
    
    # Create CUDA stream for async operations
    stream = cp.cuda.Stream()
    
    batch_count = 0
    with stream:
        for batch_payload in batch_iterator:
            batch_id = batch_payload.get('batch_id', f'batch_{batch_count}')
            batch_data = batch_payload.get('data')
            
            if batch_data is None:
                logger.warning(f"Batch {batch_id} has no data, skipping")
                continue
            
            logger.info(f"Processing batch {batch_id} for power spectrum computation")
            
            # Convert to GPU array if needed
            if isinstance(batch_data, np.ndarray):
                batch_gpu = cp.asarray(batch_data, stream=stream)
            else:
                batch_gpu = batch_data
            
            # Compute FFT on GPU
            field_spectral = cp.fft.fftn(batch_gpu, norm="ortho")
            
            # Compute power spectrum: P(k) = |F(k)|²
            power = cp.abs(field_spectral) ** 2
            
            # Compute radial power spectrum for this batch
            k_centers, Pk = _radial_bin_gpu_batched(
                power, domain.shape, bins, stream
            )
            
            # Convert to CPU for accumulation
            k_centers_cpu = cp.asnumpy(k_centers, stream=stream)
            Pk_cpu = cp.asnumpy(Pk, stream=stream)
            
            all_k_centers.append(k_centers_cpu)
            all_Pk_values.append(Pk_cpu)
            
            batch_count += 1
            
            # Log batch completion
            logger.debug(
                f"Batch {batch_id} completed: {len(k_centers_cpu)} bins, "
                f"Pk range=[{Pk_cpu.min():.2e}, {Pk_cpu.max():.2e}]"
            )
    
    # Synchronize stream
    stream.synchronize()
    
    if not all_k_centers:
        raise ValueError("No valid batches processed for power spectrum computation")
    
    # Combine results from all batches
    # Use first batch's k_centers as reference (should be same for all)
    k_centers_ref = all_k_centers[0]
    
    # Average power spectra across batches
    Pk_combined = np.zeros_like(k_centers_ref)
    for Pk in all_Pk_values:
        # Interpolate to reference k_centers if needed
        if len(Pk) == len(k_centers_ref):
            Pk_combined += Pk
        else:
            # Simple interpolation (assumes similar k ranges)
            Pk_combined += np.interp(k_centers_ref, all_k_centers[all_Pk_values.index(Pk)], Pk)
    
    Pk_combined /= len(all_Pk_values)
    
    logger.info(
        f"Batched power spectrum computation completed: "
        f"{batch_count} batches, {len(k_centers_ref)} bins"
    )
    
    return {"k": k_centers_ref, "P": Pk_combined}


def _radial_bin_gpu_batched(
    power: cp.ndarray,
    domain_shape: Tuple[int, ...],
    bins: int,
    stream: Optional[cp.cuda.Stream] = None,
) -> Tuple[cp.ndarray, cp.ndarray]:
    """
    Compute radial binning of power spectrum on GPU.
    
    Physical Meaning:
        Bins power spectrum P(k) by wave number magnitude |k| for isotropic
        power spectrum computation.
        
    Args:
        power (cp.ndarray): Power spectrum |F(k)|² on GPU.
        domain_shape (Tuple[int, ...]): Domain shape for wave vector calculation.
        bins (int): Number of bins for radial averaging.
        stream (Optional[cp.cuda.Stream]): CUDA stream for async operations.
            
    Returns:
        Tuple[cp.ndarray, cp.ndarray]: (k_centers, Pk) on GPU.
    """
    # Build k-grid for spatial dimensions (first 3)
    if len(domain_shape) >= 3:
        kx = cp.fft.fftfreq(domain_shape[0], 1.0 / domain_shape[0])
        ky = cp.fft.fftfreq(domain_shape[1], 1.0 / domain_shape[1])
        kz = cp.fft.fftfreq(domain_shape[2], 1.0 / domain_shape[2])
        
        # Create meshgrid on GPU
        KX, KY, KZ = cp.meshgrid(kx, ky, kz, indexing="ij", sparse=False)
        k_magnitude = cp.sqrt(KX**2 + KY**2 + KZ**2)
        
        # Extract spatial slice if power is 7D
        if power.ndim == 7:
            # Take first slice of phase and time dimensions
            power_3d = power[:, :, :, 0, 0, 0, 0]
        elif power.ndim == 3:
            power_3d = power
        else:
            # Flatten to 3D equivalent
            power_3d = power.reshape(domain_shape[:3])
            k_magnitude = k_magnitude.reshape(domain_shape[:3])
    else:
        # Lower dimensional case
        k_magnitude = cp.abs(cp.fft.fftfreq(domain_shape[0], 1.0 / domain_shape[0]))
        power_3d = power.flatten()
        k_magnitude = k_magnitude.flatten()
    
    # Bin by |k|
    k_flat = k_magnitude.ravel()
    p_flat = power_3d.ravel()
    
    k_max = float(cp.max(k_flat).get())
    nbins = min(bins, max(32, int(cp.cbrt(power_3d.size).get())))
    bin_edges = cp.linspace(0.0, k_max, nbins + 1)
    
    # Digitize for binning
    digitized = cp.digitize(k_flat, bin_edges) - 1
    digitized = cp.clip(digitized, 0, nbins - 1)
    
    # Compute binned power spectrum
    Pk = cp.zeros(nbins, dtype=power.dtype)
    counts = cp.zeros(nbins, dtype=cp.int32)
    
    for i in range(nbins):
        mask = digitized == i
        if cp.any(mask).get():
            Pk[i] = cp.mean(p_flat[mask])
            counts[i] = cp.sum(mask)
    
    # Bin centers
    k_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    
    # Normalize by counts and filter non-zero bins
    nonzero = counts > 0
    Pk = Pk[nonzero]
    k_centers = k_centers[nonzero]
    
    return k_centers, Pk

