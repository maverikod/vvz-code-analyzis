"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core batch processing methods for batched FFT operations.

This module provides core methods for processing batches of fields
using CUDA and CPU backends.
"""

import logging
from typing import List
import numpy as np

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class BatchedFFTCore:
    """
    Core batch processing methods for batched FFT operations.
    
    Physical Meaning:
        Provides core methods for processing batches of fields using
        CUDA and CPU backends with vectorized operations.
    """
    
    @staticmethod
    def process_batch_cuda(
        batch_fields: List[np.ndarray],
        dtype: np.dtype,
        normalization: str,
        forward: bool,
    ) -> List[np.ndarray]:
        """
        Process batch of fields on GPU using CUDA.
        
        Physical Meaning:
            Performs FFT operations on batch of fields using GPU acceleration
            with vectorized operations for optimal performance.
            
        Args:
            batch_fields (List[np.ndarray]): Batch of fields to process.
            dtype (np.dtype): Data type for computations.
            normalization (str): FFT normalization mode.
            forward (bool): True for forward FFT, False for inverse FFT.
            
        Returns:
            List[np.ndarray]: Processed fields.
        """
        # Convert to GPU arrays
        batch_gpu = [cp.asarray(field, dtype=dtype) for field in batch_fields]
        
        # Stack for vectorized processing
        stacked = cp.stack(batch_gpu)
        
        # Perform FFT
        if forward:
            result_stacked = cp.fft.fftn(
                stacked, axes=tuple(range(1, stacked.ndim)), norm=normalization
            )
        else:
            result_stacked = cp.fft.ifftn(
                stacked, axes=tuple(range(1, stacked.ndim)), norm=normalization
            )
        
        # Convert back to CPU using vectorized operation
        # Use asnumpy on entire stack for better performance
        result_stacked_cpu = cp.asnumpy(result_stacked)
        
        # Split using vectorized indexing
        results = [result_stacked_cpu[i] for i in range(len(batch_fields))]
        
        # Clean up GPU memory
        del batch_gpu, stacked, result_stacked
        cp.get_default_memory_pool().free_all_blocks()
        
        return results
    
    @staticmethod
    def process_batch_cpu(
        batch_fields: List[np.ndarray],
        normalization: str,
        forward: bool,
    ) -> List[np.ndarray]:
        """
        Process batch of fields on CPU.
        
        Physical Meaning:
            Performs FFT operations on batch of fields using CPU with
            vectorized NumPy operations.
            
        Args:
            batch_fields (List[np.ndarray]): Batch of fields to process.
            normalization (str): FFT normalization mode.
            forward (bool): True for forward FFT, False for inverse FFT.
            
        Returns:
            List[np.ndarray]: Processed fields.
        """
        # Stack for vectorized processing
        stacked = np.stack(batch_fields)
        
        # Perform FFT
        if forward:
            result_stacked = np.fft.fftn(
                stacked, axes=tuple(range(1, stacked.ndim)), norm=normalization
            )
        else:
            result_stacked = np.fft.ifftn(
                stacked, axes=tuple(range(1, stacked.ndim)), norm=normalization
            )
        
        # Split back into individual fields
        results = [result_stacked[i] for i in range(len(batch_fields))]
        
        return results

