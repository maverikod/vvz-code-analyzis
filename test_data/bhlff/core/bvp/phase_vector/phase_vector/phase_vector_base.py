"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for phase vector.

This module provides the base PhaseVectorBase class with common
initialization and main methods.
"""

import numpy as np
from typing import Dict, Any
import logging

from bhlff.core.domain import Domain
from bhlff.core.bvp.bvp_constants import BVPConstants
from ..phase_components import PhaseComponents
from ..electroweak_coupling import ElectroweakCoupling

# CUDA optimization
try:
    import cupy as cp
    CUDA_AVAILABLE = True
    logging.info("CUDA support enabled with CuPy")
except ImportError:
    CUDA_AVAILABLE = False
    logging.warning("CUDA not available, falling back to CPU")
    cp = None

# Memory monitoring
try:
    from bhlff.utils.memory_monitor import MemoryMonitor, memory_monitor_context
    MEMORY_MONITORING_AVAILABLE = True
except ImportError:
    MEMORY_MONITORING_AVAILABLE = False
    logging.warning("Memory monitoring not available")
    MemoryMonitor = None


class PhaseVectorBase:
    """
    Base class for U(1)³ phase vector structure.
    
    Physical Meaning:
        Provides base functionality for the three-component phase vector Θ_a (a=1..3)
        that represents the fundamental phase structure of the BVP field.
        
    Mathematical Foundation:
        The phase vector Θ = (Θ₁, Θ₂, Θ₃) represents three independent
        U(1) phase degrees of freedom with weak hierarchical coupling
        to SU(2)/core through invariant mixed terms.
    """
    
    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ) -> None:
        """
        Initialize U(1)³ phase vector structure.
        
        Physical Meaning:
            Sets up the three-component phase vector Θ_a (a=1..3)
            with proper U(1)³ structure and weak SU(2) coupling.
            
        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Phase vector configuration including:
                - phase_amplitudes: Amplitudes for each phase component
                - phase_frequencies: Frequencies for each phase component
                - su2_coupling_strength: Strength of SU(2) coupling
                - electroweak_coefficients: Electroweak coupling parameters
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants or BVPConstants(config)
        
        # CUDA optimization setup
        self.cuda_available = CUDA_AVAILABLE
        self.use_cuda = config.get("use_cuda", True) and self.cuda_available
        self.logger = logging.getLogger(__name__)
        
        # Memory monitoring setup
        self.memory_monitoring_available = MEMORY_MONITORING_AVAILABLE
        self.enable_memory_monitoring = config.get("enable_memory_monitoring", True)
        self.memory_monitor = None
        
        if self.memory_monitoring_available and self.enable_memory_monitoring and MemoryMonitor:
            self.memory_monitor = MemoryMonitor(log_interval=0.5)
            self.logger.info("PhaseVector: Memory monitoring enabled")
        
        if self.use_cuda:
            self.logger.info("PhaseVector: CUDA optimization enabled")
        else:
            self.logger.info("PhaseVector: Using CPU computation")
        
        # Initialize components
        self._phase_components = PhaseComponents(domain, config)
        self._electroweak_coupling = ElectroweakCoupling(config)
        
        # Setup SU(2) coupling
        self._setup_su2_coupling()
    
    def _setup_su2_coupling(self) -> None:
        """
        Setup weak hierarchical coupling to SU(2)/core.
        
        Physical Meaning:
            Establishes the weak hierarchical coupling between
            the U(1)³ phase structure and SU(2)/core through
            invariant mixed terms.
        """
        su2_config = self.config.get("su2_coupling", {})
        coupling_strength = su2_config.get("coupling_strength", 0.1)
        
        # Create SU(2) coupling matrix (weak coupling)
        # This represents the invariant mixed terms between U(1)³ and SU(2)
        self.coupling_matrix = np.array(
            [
                [1.0, coupling_strength, 0.0],
                [coupling_strength, 1.0, coupling_strength],
                [0.0, coupling_strength, 1.0],
            ],
            dtype=complex,
        )
        
        # Add weak coupling terms
        self.su2_coupling_terms = {
            "theta_1_theta_2": coupling_strength * 0.1,
            "theta_2_theta_3": coupling_strength * 0.1,
            "theta_1_theta_3": coupling_strength * 0.05,  # Weaker coupling
        }
    
    def get_su2_coupling_strength(self) -> float:
        """
        Get the SU(2) coupling strength.
        
        Physical Meaning:
            Returns the strength of the weak hierarchical
            coupling to SU(2)/core.
            
        Returns:
            float: SU(2) coupling strength.
        """
        return np.abs(self.coupling_matrix[0, 1])  # Off-diagonal element
    
    def set_su2_coupling_strength(self, strength: float) -> None:
        """
        Set the SU(2) coupling strength.
        
        Physical Meaning:
            Updates the strength of the weak hierarchical
            coupling to SU(2)/core.
            
        Args:
            strength (float): New SU(2) coupling strength.
        """
        # Update coupling matrix
        self.coupling_matrix[0, 1] = strength
        self.coupling_matrix[1, 0] = strength
        self.coupling_matrix[1, 2] = strength
        self.coupling_matrix[2, 1] = strength
        
        # Update coupling terms
        self.su2_coupling_terms["theta_1_theta_2"] = strength * 0.1
        self.su2_coupling_terms["theta_2_theta_3"] = strength * 0.1
        self.su2_coupling_terms["theta_1_theta_3"] = strength * 0.05
    
    def get_electroweak_coefficients(self) -> Dict[str, float]:
        """
        Get electroweak coupling coefficients.
        
        Physical Meaning:
            Returns the current electroweak coupling coefficients
            used for current calculations.
            
        Returns:
            Dict[str, float]: Electroweak coupling coefficients.
        """
        return self._electroweak_coupling.get_electroweak_coefficients()
    
    def set_electroweak_coefficients(self, coefficients: Dict[str, float]) -> None:
        """
        Set electroweak coupling coefficients.
        
        Physical Meaning:
            Updates the electroweak coupling coefficients
            used for current calculations.
            
        Args:
            coefficients (Dict[str, float]): New coupling coefficients.
        """
        self._electroweak_coupling.set_electroweak_coefficients(coefficients)
    
    def __repr__(self) -> str:
        """String representation of phase vector."""
        coupling_strength = self.get_su2_coupling_strength()
        em_coupling = self.get_electroweak_coefficients()["em_coupling"]
        cuda_status = "CUDA" if self.use_cuda else "CPU"
        return (
            f"PhaseVector(domain={self.domain}, "
            f"su2_coupling={coupling_strength:.3f}, "
            f"em_coupling={em_coupling:.3f}, "
            f"compute={cuda_status})"
        )

