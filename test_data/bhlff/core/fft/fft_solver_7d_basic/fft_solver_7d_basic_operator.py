"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral operator application methods for FFT solver 7D basic.

This module provides spectral operator application methods as a mixin class.
"""

import numpy as np
import logging
import sys
from itertools import product

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class FFTSolver7DBasicOperatorMixin:
    """Mixin providing spectral operator application methods."""
    
    def _apply_spectral_operator_lazy(self, field_hat: np.ndarray) -> np.ndarray:
        """
        Apply spectral operator using lazy coefficient computation.
        
        Physical Meaning:
            Computes spectral coefficients on-the-fly for each element,
            avoiding storage of full 7D coefficient array.
        """
        logger.info(f"[SOLVER LAZY] _apply_spectral_operator_lazy: START - shape={field_hat.shape}")
        sys.stdout.flush()
        
        # Get wave number arrays
        kx, ky, kz, p1, p2, p3, kt = self._k_arrays  # type: ignore
        
        # Create meshgrids on-the-fly (this is still memory-intensive but necessary)
        # For very large arrays, we need to process in blocks
        shape = field_hat.shape
        
        # Check if we need block processing even for lazy evaluation
        field_memory = field_hat.nbytes
        logger.info(f"[SOLVER LAZY] Field memory: {field_memory/1e9:.2f}GB")
        sys.stdout.flush()
        
        if PSUTIL_AVAILABLE:
            available_memory = psutil.virtual_memory().available
            logger.info(f"[SOLVER LAZY] Available memory: {available_memory/1e9:.2f}GB")
            sys.stdout.flush()
            if field_memory * 2 > 0.5 * available_memory:  # Need 2x for meshgrids
                # Use block processing
                logger.info(f"[SOLVER LAZY] Using block processing (field too large)")
                sys.stdout.flush()
                return self._apply_spectral_operator_blocked(field_hat)
        
        logger.info(f"[SOLVER LAZY] Creating meshgrids via broadcasting...")
        sys.stdout.flush()
        
        # Compute coefficients on-the-fly using broadcasting
        KX = kx[:, None, None, None, None, None, None]
        KY = ky[None, :, None, None, None, None, None]
        KZ = kz[None, None, :, None, None, None, None]
        P1 = p1[None, None, None, :, None, None, None]
        P2 = p2[None, None, None, None, :, None, None]
        P3 = p3[None, None, None, None, None, :, None]
        KT = kt[None, None, None, None, None, None, :]
        
        logger.info(f"[SOLVER LAZY] Computing k^2...")
        sys.stdout.flush()
        k2 = KX**2 + KY**2 + KZ**2 + P1**2 + P2**2 + P3**2 + KT**2
        
        logger.info(f"[SOLVER LAZY] Computing coefficients...")
        sys.stdout.flush()
        k_magnitude = np.sqrt(k2 + 1e-15)
        coeffs = self._mu * (k_magnitude ** (2 * self._beta)) + self._lambda
        
        if self._lambda == 0.0:
            coeffs = np.where(k2 == 0, 1.0, coeffs)
        
        logger.info(f"[SOLVER LAZY] Applying operator...")
        sys.stdout.flush()
        result = field_hat / coeffs
        
        logger.info(f"[SOLVER LAZY] _apply_spectral_operator_lazy: COMPLETE")
        sys.stdout.flush()
        return result
    
    def _apply_spectral_operator_blocked(self, field_hat: np.ndarray) -> np.ndarray:
        """
        Apply spectral operator using block processing for very large fields.
        
        Physical Meaning:
            Processes field in blocks to avoid memory issues while computing
            spectral coefficients on-the-fly for each block.
        """
        # Determine block size based on available memory
        field_memory = field_hat.nbytes
        if PSUTIL_AVAILABLE:
            available_memory = psutil.virtual_memory().available
            # Use blocks that fit in 10% of available memory
            block_memory = 0.1 * available_memory
        else:
            block_memory = 1e9  # 1GB default
        
        # Calculate block size per dimension
        bytes_per_element = 16  # complex128
        elements_per_block = int(block_memory / bytes_per_element)
        block_size_per_dim = int(elements_per_block ** (1.0 / len(field_hat.shape)))
        block_size_per_dim = max(8, min(block_size_per_dim, 64))  # Reasonable bounds
        
        shape = field_hat.shape
        result = np.zeros_like(field_hat)
        
        # Get wave number arrays
        kx, ky, kz, p1, p2, p3, kt = self._k_arrays  # type: ignore
        
        # Process in blocks
        num_blocks = tuple((s + block_size_per_dim - 1) // block_size_per_dim for s in shape)
        
        for block_idx in product(*[range(n) for n in num_blocks]):
            # Compute block slices
            slices = tuple(
                slice(
                    block_idx[i] * block_size_per_dim,
                    min((block_idx[i] + 1) * block_size_per_dim, shape[i])
                )
                for i in range(len(shape))
            )
            
            # Extract block
            block = field_hat[slices]
            
            # Compute coefficients for this block
            block_kx = kx[slices[0]]
            block_ky = ky[slices[1]]
            block_kz = kz[slices[2]]
            block_p1 = p1[slices[3]]
            block_p2 = p2[slices[4]]
            block_p3 = p3[slices[5]]
            block_kt = kt[slices[6]]
            
            # Create meshgrids for block
            KX = block_kx[:, None, None, None, None, None, None]
            KY = block_ky[None, :, None, None, None, None, None]
            KZ = block_kz[None, None, :, None, None, None, None]
            P1 = block_p1[None, None, None, :, None, None, None]
            P2 = block_p2[None, None, None, None, :, None, None]
            P3 = block_p3[None, None, None, None, None, :, None]
            KT = block_kt[None, None, None, None, None, None, :]
            
            k2 = KX**2 + KY**2 + KZ**2 + P1**2 + P2**2 + P3**2 + KT**2
            k_magnitude = np.sqrt(k2 + 1e-15)
            coeffs = self._mu * (k_magnitude ** (2 * self._beta)) + self._lambda
            
            if self._lambda == 0.0:
                coeffs = np.where(k2 == 0, 1.0, coeffs)
            
            # Apply operator and store result
            result[slices] = block / coeffs
        
        return result

