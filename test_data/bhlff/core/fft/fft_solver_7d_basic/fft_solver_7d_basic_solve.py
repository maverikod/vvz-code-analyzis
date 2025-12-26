"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Solving methods for FFT solver 7D basic.

This module provides solving methods as a mixin class.
"""

from typing import Union, Iterator, Dict, Any, Optional
import numpy as np
import logging
import sys

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ...exceptions import CUDANotAvailableError
from bhlff.utils.cuda_backend import CUDABackend

logger = logging.getLogger(__name__)


class FFTSolver7DBasicSolveMixin:
    """Mixin providing solving methods."""
    
    def solve_stationary(self, source_field: Union[np.ndarray, 'FieldArray']) -> 'FieldArray':
        """
        Solve stationary phase field equation.
        
        Physical Meaning:
            Solves the fractional Laplacian equation L_β a = s for given source,
            returning solution as FieldArray that may be swapped to disk.
        """
        logger.info(f"[SOLVER] solve_stationary: ENTRY - source_field type={type(source_field)}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        from ...arrays.field_array import FieldArray
        
        logger.info(f"[SOLVER] solve_stationary: STEP 0.1: Preparing source field...")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # For FieldArray, pass it directly to forward_fft to enable streaming
        # For regular numpy arrays, convert to complex128
        if isinstance(source_field, FieldArray):
            source_for_fft = source_field
            source_array = source_field.array
            logger.info(f"[SOLVER] solve_stationary: STEP 0.1 COMPLETE: Using FieldArray directly for streaming")
        else:
            source_array = source_field
            # Convert to complex128 for FFT
            if not np.iscomplexobj(source_array):
                source_for_fft = np.asarray(source_array, dtype=np.complex128)
            else:
                source_for_fft = np.asarray(source_array, dtype=np.complex128)
            logger.info(f"[SOLVER] solve_stationary: STEP 0.1 COMPLETE: Using as numpy array")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Validate shape
        if source_array is None:
            raise ValueError("source_field must not be None")
        if tuple(source_array.shape) != tuple(getattr(self.domain, "shape")):
            raise ValueError(
                f"Source shape {source_array.shape} incompatible with domain shape {self.domain.shape}"
            )
        
        # Always operate through unified ops (handles GPU/CPU and OOM fallback)
        source_size_mb = source_array.nbytes / (1024**2)
        logger.info(
            f"[SOLVER] solve_stationary: START - source {source_array.shape} "
            f"({source_size_mb:.2f}MB), use_cuda={self.use_cuda}, "
            f"is_FieldArray={isinstance(source_field, FieldArray)}"
        )
        sys.stdout.flush()
        
        logger.info(f"[SOLVER] STEP 1: Performing forward FFT...")
        sys.stdout.flush()
        # Pass FieldArray directly to enable streaming for swapped fields
        s_hat = self._ops.forward_fft(source_for_fft, "ortho")
        logger.info(f"[SOLVER] STEP 1 COMPLETE: Forward FFT completed, spectral shape: {s_hat.shape}")
        sys.stdout.flush()
        
        # CRITICAL: Check for zero-mode (DC component) when lambda=0
        # If lambda=0 and source has non-zero DC component, division by zero will occur
        if self.lmbda == 0.0:
            # Check DC component (all indices = 0)
            dc_idx = tuple([0] * len(s_hat.shape))
            dc_component = s_hat[dc_idx]
            if abs(dc_component) > 1e-12:  # Non-zero DC component
                raise ZeroDivisionError(
                    f"lambda=0 with non-zero zero-mode in source: ŝ(0)={dc_component:.6e}≠0. "
                    f"Source must have zero DC component when lambda=0 to avoid division by zero."
                )
        
        # Apply spectral operator - use lazy evaluation if needed
        logger.info(f"[SOLVER] STEP 2: Applying spectral operator...")
        sys.stdout.flush()
        if self._use_lazy_coeffs:
            a_hat = self._apply_spectral_operator_lazy(s_hat)
        else:
            if self._coeffs is None:
                logger.info(f"[SOLVER] Building spectral coefficients...")
                sys.stdout.flush()
                self._build_spectral_coefficients()
            a_hat = s_hat / self._coeffs
        
        logger.info(f"[SOLVER] STEP 2 COMPLETE: Spectral operator applied")
        sys.stdout.flush()
        
        logger.info(f"[SOLVER] STEP 3: Performing inverse FFT...")
        sys.stdout.flush()
        # CRITICAL: Do not take .real here - preserve complex solution for complex sources
        # For complex sources (e.g., plane waves exp(i*k*x)), the solution must be complex
        # to preserve phase information (critical for EM fields, wave physics, etc.)
        # Only take .real if source is explicitly real-valued
        a = self._ops.inverse_fft(a_hat, "ortho")
        # Check if source is real - if so, solution should also be real (within numerical precision)
        if np.isrealobj(source_array):
            # Source is real, so solution should be real (IFFT of Hermitian spectrum)
            # Take real part to remove numerical noise in imaginary part
            a = a.real
        # Otherwise, keep complex solution for complex sources
        logger.info(f"[SOLVER] STEP 3 COMPLETE: Inverse FFT completed, solution shape: {a.shape}, dtype: {a.dtype}")
        sys.stdout.flush()
        
        # Return as FieldArray for transparent swap support
        return FieldArray(array=a)
    
    def _apply_preconditioner_batches(
        self,
        batch_iterator: Iterator[Dict[str, Any]],
        gpu_memory_ratio: float = 0.8,
    ) -> Iterator[Dict[str, Any]]:
        """
        Apply preconditioner to batches of residuals with CUDA streams.
        
        Physical Meaning:
            Applies preconditioner M⁻¹ to batches of residuals for iterative
            solving methods. Each batch is processed independently using CUDA
            streams for parallel execution and optimal GPU utilization.
            
        Mathematical Foundation:
            For each batch residual r_batch:
            - Preconditioned residual: M⁻¹ r_batch
            - Preconditioner: M⁻¹ = (μ|k|^(2β) + λ)⁻¹ in spectral space
            - Operations use 80% GPU memory per batch
            
        Args:
            batch_iterator (Iterator[Dict[str, Any]]): Iterator yielding batches
                with keys:
                - 'batch_id': Unique batch identifier for logging
                - 'data': Residual data (np.ndarray or cp.ndarray)
                - 'slices': Slice indices for this batch (optional)
            gpu_memory_ratio (float): GPU memory ratio to use per batch (default: 0.8).
                
        Yields:
            Dict[str, Any]: Preconditioned batch with same structure as input,
                with 'data' containing preconditioned residual.
                
        Raises:
            CUDANotAvailableError: If CUDA is not available (required for batched ops).
        """
        CUDABackend.require_cuda()
        
        if not CUDA_AVAILABLE:
            raise CUDANotAvailableError(
                "CUDA is required for batched preconditioner application. "
                "CPU fallback is NOT ALLOWED. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        logger.info(
            f"Starting batched preconditioner application with "
            f"gpu_memory_ratio={gpu_memory_ratio:.1%}"
        )
        
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
                
                logger.info(f"Processing batch {batch_id} for preconditioner application")
                
                # Convert to GPU array if needed
                if isinstance(batch_data, np.ndarray):
                    residual_gpu = cp.asarray(batch_data, stream=stream)
                else:
                    residual_gpu = batch_data
                
                # Transform to spectral space
                residual_hat = cp.fft.fftn(residual_gpu, norm="ortho", stream=stream)
                
                # Apply preconditioner in spectral space
                # Preconditioner: M⁻¹ = (μ|k|^(2β) + λ)⁻¹
                # For batched processing, we need to compute coefficients for this batch
                # Use lazy coefficient computation if available
                if hasattr(self, '_apply_spectral_operator_lazy'):
                    # Apply inverse operator (preconditioner)
                    # M⁻¹ r = r / (μ|k|^(2β) + λ)
                    # This is equivalent to solving M x = r, so x = M⁻¹ r
                    preconditioned_hat = self._apply_preconditioner_spectral_lazy(
                        residual_hat, stream
                    )
                else:
                    # Fallback: use precomputed coefficients if available
                    if hasattr(self, '_coeffs') and self._coeffs is not None:
                        coeffs_gpu = cp.asarray(self._coeffs, stream=stream)
                        # Extract slice if needed
                        if batch_payload.get('slices') is not None:
                            slices = batch_payload['slices']
                            coeffs_gpu = coeffs_gpu[slices]
                        preconditioned_hat = residual_hat / coeffs_gpu
                    else:
                        # Build coefficients on-the-fly for this batch
                        preconditioned_hat = self._apply_preconditioner_spectral_lazy(
                            residual_hat, stream
                        )
                
                # Transform back to real space
                preconditioned = cp.fft.ifftn(
                    preconditioned_hat, norm="ortho", stream=stream
                )
                
                # Convert to CPU if needed
                if isinstance(batch_data, np.ndarray):
                    preconditioned_cpu = cp.asnumpy(preconditioned, stream=stream)
                else:
                    preconditioned_cpu = preconditioned
                
                # Create output batch payload
                output_payload = batch_payload.copy()
                output_payload['data'] = preconditioned_cpu
                
                batch_count += 1
                
                logger.debug(
                    f"Batch {batch_id} preconditioner application completed: "
                    f"shape={preconditioned_cpu.shape}"
                )
                
                yield output_payload
        
        # Synchronize stream
        stream.synchronize()
        
        logger.info(
            f"Batched preconditioner application completed: {batch_count} batches"
        )
    
    def _apply_preconditioner_spectral_lazy(
        self,
        residual_hat: "cp.ndarray",
        stream: Optional["cp.cuda.Stream"] = None,
    ) -> "cp.ndarray":
        """
        Apply preconditioner in spectral space using lazy coefficient computation.
        
        Physical Meaning:
            Computes preconditioned residual M⁻¹ r in spectral space by dividing
            by spectral coefficients (μ|k|^(2β) + λ).
            
        Args:
            residual_hat (cp.ndarray): Residual in spectral space on GPU.
            stream (Optional[cp.cuda.Stream]): CUDA stream for async operations.
                
        Returns:
            cp.ndarray: Preconditioned residual in spectral space.
        """
        # Get wave number arrays (should be available from solver)
        if not hasattr(self, '_k_arrays'):
            raise AttributeError(
                "Solver must have _k_arrays attribute for lazy preconditioner"
            )
        
        kx, ky, kz, p1, p2, p3, kt = self._k_arrays  # type: ignore
        
        # Create meshgrids using broadcasting (memory-efficient)
        shape = residual_hat.shape
        KX = cp.asarray(kx, dtype=cp.complex128)[:, None, None, None, None, None, None]
        KY = cp.asarray(ky, dtype=cp.complex128)[None, :, None, None, None, None, None]
        KZ = cp.asarray(kz, dtype=cp.complex128)[None, None, :, None, None, None, None]
        P1 = cp.asarray(p1, dtype=cp.complex128)[None, None, None, :, None, None, None]
        P2 = cp.asarray(p2, dtype=cp.complex128)[None, None, None, None, :, None, None]
        P3 = cp.asarray(p3, dtype=cp.complex128)[None, None, None, None, None, :, None]
        KT = cp.asarray(kt, dtype=cp.complex128)[None, None, None, None, None, None, :]
        
        # Compute k^2 and coefficients
        k2 = KX**2 + KY**2 + KZ**2 + P1**2 + P2**2 + P3**2 + KT**2
        k_magnitude = cp.sqrt(k2 + 1e-15)
        coeffs = self._mu * (k_magnitude ** (2 * self._beta)) + self._lambda
        
        if self._lambda == 0.0:
            coeffs = cp.where(k2 == 0, 1.0, coeffs)
        
        # Apply preconditioner: M⁻¹ r = r / coeffs
        preconditioned_hat = residual_hat / coeffs
        
        return preconditioned_hat
    
    # Backward-compatible API expected by tests
    def solve(self, source_field: np.ndarray) -> np.ndarray:
        """Backward-compatible solve method."""
        result = self.solve_stationary(source_field)
        if hasattr(result, "array"):
            return result.array
        return result

