"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA methods for phase vector.

This module provides CUDA computation methods as a mixin class.
"""

import numpy as np
from typing import Optional, Union

# CUDA optimization
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class PhaseVectorCUDAMixin:
    """Mixin providing CUDA computation methods."""
    
    def _to_gpu(self, array: np.ndarray) -> Union["cp.ndarray", np.ndarray]:
        """
        Convert numpy array to GPU array.
        
        Physical Meaning:
            Transfers array to GPU memory for CUDA computation.
            
        Args:
            array (np.ndarray): Input array.
            
        Returns:
            cp.ndarray: GPU array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.asarray(array)
        return array
    
    def _to_cpu(self, array) -> np.ndarray:
        """
        Convert GPU array to numpy array.
        
        Physical Meaning:
            Transfers array from GPU memory to CPU memory.
            
        Args:
            array: Input array (GPU or CPU).
            
        Returns:
            np.ndarray: CPU array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None and hasattr(array, "get"):
            return array.get()
        return array
    
    def _cuda_gradient(self, array, axis: int = 0) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute gradient using CUDA.
        
        Physical Meaning:
            Computes gradient using CUDA for optimal performance.
            
        Args:
            array: Input array.
            axis (int): Axis along which to compute gradient.
            
        Returns:
            cp.ndarray: Gradient array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.gradient(array, axis=axis)
        return np.gradient(array, axis=axis)
    
    def _cuda_abs(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute absolute value using CUDA.
        
        Physical Meaning:
            Computes absolute value using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Absolute value array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.abs(array)
        return np.abs(array)
    
    def _cuda_angle(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute angle using CUDA.
        
        Physical Meaning:
            Computes angle using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Angle array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.angle(array)
        return np.angle(array)
    
    def _cuda_exp(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute exponential using CUDA.
        
        Physical Meaning:
            Computes exponential using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Exponential array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.exp(array)
        return np.exp(array)
    
    def _cuda_sum(self, array, axis: Optional[int] = None) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute sum using CUDA.
        
        Physical Meaning:
            Computes sum using CUDA for optimal performance.
            
        Args:
            array: Input array.
            axis: Axis along which to sum.
            
        Returns:
            cp.ndarray: Sum array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.sum(array, axis=axis)
        return np.sum(array, axis=axis)
    
    def _cuda_mean(self, array, axis: Optional[int] = None) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute mean using CUDA.
        
        Physical Meaning:
            Computes mean using CUDA for optimal performance.
            
        Args:
            array: Input array.
            axis: Axis along which to compute mean.
            
        Returns:
            cp.ndarray: Mean array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.mean(array, axis=axis)
        return np.mean(array, axis=axis)
    
    def _cuda_sqrt(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute square root using CUDA.
        
        Physical Meaning:
            Computes square root using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Square root array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.sqrt(array)
        return np.sqrt(array)
    
    def _cuda_sin(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute sine using CUDA.
        
        Physical Meaning:
            Computes sine using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Sine array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.sin(array)
        return np.sin(array)
    
    def _cuda_cos(self, array) -> Union["cp.ndarray", np.ndarray]:
        """
        Compute cosine using CUDA.
        
        Physical Meaning:
            Computes cosine using CUDA for optimal performance.
            
        Args:
            array: Input array.
            
        Returns:
            cp.ndarray: Cosine array.
        """
        if self.use_cuda and CUDA_AVAILABLE and cp is not None:
            return cp.cos(array)
        return np.cos(array)

