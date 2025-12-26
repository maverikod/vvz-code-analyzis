"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for BVP envelope solver.

This module provides the base BVPEnvelopeSolverBase class with common
initialization and setup methods.
"""

import numpy as np
from typing import Dict, Any
import logging

from ...domain import Domain
from ..bvp_constants import BVPConstants
from ..envelope_nonlinear_coefficients import EnvelopeNonlinearCoefficients
from ..envelope_linear_solver import EnvelopeLinearSolver
from ..memory_protection import MemoryProtector
from ..envelope_solver.envelope_solver_core import EnvelopeSolverCore
from ..envelope_solver_line_search import EnvelopeSolverLineSearch
from ..bvp_block_processing_system import BVPBlockProcessingSystem, BVPBlockConfig


class BVPEnvelopeSolverBase:
    """
    Base class for BVP envelope solver.
    
    Physical Meaning:
        Provides base functionality for solving the nonlinear 7D envelope equation
        for the Base High-Frequency Field in M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
    """
    
    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ) -> None:
        """
        Initialize envelope equation solver.
        
        Args:
            domain (Domain): Computational domain for envelope calculations.
            config (Dict[str, Any]): Envelope solver configuration.
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants or BVPConstants(config)
        self.logger = logging.getLogger(__name__)
        self._setup_parameters()
        self._setup_solver_components()
    
    def _setup_parameters(self) -> None:
        """Setup envelope equation parameters."""
        # Base parameters for nonlinear coefficient computation
        self.kappa_0 = self.constants.get_envelope_parameter("kappa_0")
        self.kappa_2 = self.constants.get_envelope_parameter("kappa_2")
        self.chi_prime = self.constants.get_envelope_parameter("chi_prime")
        self.chi_double_prime_0 = self.constants.get_envelope_parameter(
            "chi_double_prime_0"
        )
        self.k0_squared = self.constants.get_envelope_parameter("k0_squared")
        
        # Initialize nonlinear coefficients computer and linear solver
        self.nonlinear_coeffs = EnvelopeNonlinearCoefficients(self.constants)
        self.linear_solver = EnvelopeLinearSolver(self.domain, self.constants)
        
        # Initialize memory protection
        try:
            memory_threshold = self.constants.get_numerical_parameter(
                "memory_threshold"
            )
        except KeyError:
            memory_threshold = 0.8
        self.memory_protector = MemoryProtector(memory_threshold)
    
    def _setup_solver_components(self) -> None:
        """Setup solver components."""
        self._core = EnvelopeSolverCore(self.domain, self.config, self.constants)
        self._line_search = EnvelopeSolverLineSearch(self.constants)
        
        # Initialize block processing system if needed (automatic detection)
        self._block_processor = None
        self._setup_block_processing()
    
    def _setup_block_processing(self) -> None:
        """Setup block processing system if needed."""
        try:
            # Check if block processing should be enabled
            total_elements = np.prod(self.domain.shape)
            memory_threshold_elements = 1e6  # ~1M elements for complex128 = ~16MB
            
            # Check config for explicit block processing request
            use_block_processing = self.config.get("use_block_processing", None)
            if use_block_processing is None:
                use_block_processing = total_elements > memory_threshold_elements
            
            if use_block_processing:
                # Create block processing config with 80% GPU memory usage
                block_config = BVPBlockConfig(
                    max_memory_usage=0.8,  # Use 80% of available GPU memory
                    enable_gpu_acceleration=True,
                    enable_adaptive_sizing=True,
                    enable_memory_optimization=True,
                )
                self._block_processor = BVPBlockProcessingSystem(self.domain, block_config)
                self.logger.info(
                    f"Block processing initialized: "
                    f"block_size={self._block_processor.block_processor.config.max_block_size}, "
                    f"using 80% GPU memory"
                )
        except Exception as e:
            self.logger.warning(
                f"Failed to initialize block processing: {e}. "
                f"Falling back to standard processing."
            )
            self._block_processor = None
    
    def get_parameters(self) -> Dict[str, float]:
        """Get envelope equation parameters."""
        return {
            "kappa_0": self.kappa_0,
            "kappa_2": self.kappa_2,
            "chi_prime": self.chi_prime,
            "chi_double_prime_0": self.chi_double_prime_0,
            "k0_squared": self.k0_squared,
        }
    
    def get_nonlinear_coefficients(self, envelope) -> Dict[str, Any]:
        """Get nonlinear coefficients for given envelope."""
        return self.nonlinear_coeffs.compute_coefficients(envelope)
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information and usage statistics."""
        memory_info = self.memory_protector.get_memory_info()
        domain_estimate = self.memory_protector.estimate_memory_requirement(
            self.domain.shape, np.float64
        )
        
        return {
            "current_usage": memory_info,
            "domain_estimate": domain_estimate,
            "threshold": self.memory_protector.memory_threshold,
            "is_safe": self.memory_protector.check_and_warn(
                self.domain.shape, np.float64
            ),
        }
    
    def __repr__(self) -> str:
        """String representation of envelope solver."""
        return (
            f"BVPEnvelopeSolver(domain={self.domain}, "
            f"kappa_0={self.kappa_0}, kappa_2={self.kappa_2})"
        )

