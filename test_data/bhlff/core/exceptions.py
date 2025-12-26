"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Custom exceptions for BHLFF project.

This module provides specialized exceptions for CUDA-related errors and
GPU memory issues, allowing better error handling and diagnostics.

Physical Meaning:
    These exceptions represent critical failures in GPU-accelerated
    7D phase field computations, distinguishing between CUDA availability
    issues and memory constraints.
"""


class CUDANotAvailableError(RuntimeError):
    """
    Exception raised when CUDA is not available or not properly configured.
    
    Physical Meaning:
        Indicates that GPU acceleration is required but CUDA is not
        available, not properly installed, or not functional. This is a
        critical error as the project requires CUDA for all operations.
        
    Attributes:
        message (str): Detailed error message with guidance on how to resolve.
    """
    
    def __init__(self, message: str = None):
        """
        Initialize CUDA not available error.
        
        Args:
            message (str, optional): Custom error message. If not provided,
                uses default message with installation guidance.
        """
        if message is None:
            message = (
                "CUDA is not available. GPU acceleration is required. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). "
                "Verify CUDA installation with: nvidia-smi"
            )
        super().__init__(message)
        self.message = message


class InsufficientGPUMemoryError(MemoryError):
    """
    Exception raised when GPU memory is insufficient for the operation.
    
    Physical Meaning:
        Indicates that the requested operation requires more GPU memory
        than is available. This can occur when processing large 7D fields
        that exceed the GPU memory capacity, even with 80% usage limit.
        
    Attributes:
        required_memory (int): Required memory in bytes.
        available_memory (int): Available memory in bytes.
        operation_name (str): Name of the operation that failed.
        field_shape (tuple, optional): Shape of the field that caused the error.
    """
    
    def __init__(
        self,
        required_memory: int,
        available_memory: int,
        operation_name: str = "operation",
        field_shape: tuple = None,
        message: str = None
    ):
        """
        Initialize insufficient GPU memory error.
        
        Args:
            required_memory (int): Required memory in bytes.
            available_memory (int): Available memory in bytes.
            operation_name (str): Name of the operation (default: "operation").
            field_shape (tuple, optional): Shape of the field array if available.
            message (str, optional): Custom error message. If not provided,
                generates detailed message with memory information.
        """
        if message is None:
            required_gb = required_memory / 1e9
            available_gb = available_memory / 1e9
            
            message = (
                f"Insufficient GPU memory for {operation_name}. "
                f"Required: {required_gb:.2f}GB, Available: {available_gb:.2f}GB. "
            )
            
            if field_shape is not None:
                message += (
                    f"Field shape: {field_shape}. "
                    f"Consider using block-based processing with "
                    f"compute_optimal_block_tiling_7d() to process the field in blocks."
                )
            else:
                message += (
                    "Consider using block-based processing or reducing field size. "
                    "Use compute_optimal_block_tiling_7d() to compute optimal block size "
                    "for 80% GPU memory usage."
                )
        
        super().__init__(message)
        self.required_memory = required_memory
        self.available_memory = available_memory
        self.operation_name = operation_name
        self.field_shape = field_shape
        self.message = message

