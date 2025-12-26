"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for FFT solver 7D basic.

This module provides the base FFTSolver7DBasicBase class with common
initialization and setup methods.
"""

from typing import Dict, Any, Union
import numpy as np
import logging

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from ..unified_spectral_operations import UnifiedSpectralOperations

logger = logging.getLogger(__name__)


class FFTSolver7DBasicBase:
    """
    Base class for full-array FFT-based 7D solver.
    
    Physical Meaning:
        Provides base functionality for solving the stationary 7D fractional
        Riesz equation in spectral space with orthonormal FFT normalization.
    """
    
    def __init__(self, domain: "Domain", parameters: Any):
        """
        Initialize FFT solver.
        
        Args:
            domain: Computational domain.
            parameters: Solver parameters (dict or object with attributes).
        """
        self.domain = domain
        
        # Support both dict-like parameters and dataclass-style Parameters7DBVP
        if isinstance(parameters, dict):
            mu = parameters.get("mu", 1.0)
            beta = parameters.get("beta", 1.0)
            lambda_param = parameters.get("lambda", parameters.get("lambda_param", 0.0))
            use_cuda_flag = parameters.get("use_cuda", True)
        else:
            # Fallback to attribute extraction
            mu = getattr(parameters, "mu", 1.0)
            beta = getattr(parameters, "beta", 1.0)
            lambda_param = getattr(
                parameters, "lambda_param", getattr(parameters, "lambda", 0.0)
            )
            use_cuda_flag = getattr(parameters, "use_cuda", True)
        
        self.mu = float(mu)
        self.beta = float(beta)
        self.lmbda = float(lambda_param)
        self.use_cuda = bool(use_cuda_flag) and CUDA_AVAILABLE
        
        # If CUDA is required but not available, raise exception
        if use_cuda_flag and not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required but not available. "
                "Install cupy to enable GPU acceleration."
            )
        
        self._coeffs = None  # type: ignore
        self._coeff_func = None  # type: ignore
        self._use_lazy_coeffs = False
        # Use unified spectral ops to ensure proper normalization and GPU usage
        # CRITICAL: Pass use_cuda flag to ensure CUDA is used when available
        self._ops = UnifiedSpectralOperations(
            self.domain, 
            precision="float64",
            use_cuda=self.use_cuda
        )
        self._setup_spectral_coefficients()
    
    def get_spectral_coefficients(self) -> np.ndarray:
        """Get spectral coefficients."""
        return cp.asnumpy(self._coeffs) if self.use_cuda else self._coeffs  # type: ignore
    
    def get_info(self) -> dict:
        """
        Return solver diagnostic information.
        
        Returns:
            dict: Basic metadata about domain and parameters.
        """
        return {
            "solver_type": "FFTSolver7DBasic",
            "domain_shape": tuple(getattr(self.domain, "shape")),
            "mu": self.mu,
            "beta": self.beta,
            "lambda": self.lmbda,
            "use_cuda": self.use_cuda,
        }

