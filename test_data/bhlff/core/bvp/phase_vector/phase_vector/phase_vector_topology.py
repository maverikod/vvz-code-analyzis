"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological charge and coherence methods for phase vector.

This module provides methods for computing topological charge and phase coherence as a mixin class.
"""

import numpy as np
from typing import Optional

# CUDA optimization
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class PhaseVectorTopologyMixin:
    """Mixin providing topological charge and coherence methods."""
    
    def compute_topological_charge(self, envelope: Optional[np.ndarray] = None) -> float:
        """
        Compute topological charge of the phase structure.
        
        Physical Meaning:
            Computes the topological charge (winding number) of the U(1)³
            phase structure, which is quantized according to the theory.
            
        Mathematical Foundation:
            Topological charge = (1/2π) ∮ ∇φ · dl
            where φ is the total phase and the integral is over a closed loop.
            
        Args:
            envelope (np.ndarray, optional): BVP envelope field. If None, uses current phase components.
            
        Returns:
            float: Topological charge (should be quantized).
        """
        # Check memory usage before computation
        self._check_memory_usage("topological_charge_start")
        
        try:
            if envelope is not None:
                # Extract total phase from envelope
                envelope_gpu = self._to_gpu(envelope)
                total_phase = self._cuda_angle(envelope_gpu)
            else:
                # Use current phase components
                total_phase = self._phase_components.get_total_phase()
                total_phase = self._to_gpu(total_phase)
            
            # Compute topological charge using gradient
            if self.domain.dimensions == 1:
                # 1D case
                phase_gradient = self._cuda_gradient(total_phase)
                topological_charge = self._cuda_sum(phase_gradient) / (2 * np.pi)
            elif self.domain.dimensions == 2:
                # 2D case - use line integral around boundary
                phase_gradient_x = self._cuda_gradient(total_phase, axis=0)
                phase_gradient_y = self._cuda_gradient(total_phase, axis=1)
                
                # Compute line integral around boundary
                boundary_integral = 0.0
                # Top boundary
                boundary_integral += self._cuda_sum(phase_gradient_x[0, :])
                # Right boundary
                boundary_integral += self._cuda_sum(phase_gradient_y[:, -1])
                # Bottom boundary
                boundary_integral += self._cuda_sum(-phase_gradient_x[-1, :])
                # Left boundary
                boundary_integral += self._cuda_sum(-phase_gradient_y[:, 0])
                
                topological_charge = boundary_integral / (2 * np.pi)
            else:
                # 3D case - use surface integral
                phase_gradient_x = self._cuda_gradient(total_phase, axis=0)
                phase_gradient_y = self._cuda_gradient(total_phase, axis=1)
                phase_gradient_z = self._cuda_gradient(total_phase, axis=2)
                
                # Compute surface integral (simplified)
                surface_integral = self._cuda_sum(
                    phase_gradient_x + phase_gradient_y + phase_gradient_z
                )
                topological_charge = surface_integral / (2 * np.pi)
            
            # Check memory usage after computation
            self._check_memory_usage("topological_charge_end")
            
            # Convert to CPU and return scalar
            return float(self._to_cpu(topological_charge))
        
        except Exception as e:
            self.logger.error(f"Error in topological charge computation: {e}")
            # Force memory cleanup on error
            self.force_memory_cleanup()
            raise
    
    def compute_phase_coherence(self, envelope: Optional[np.ndarray] = None) -> float:
        """
        Compute phase coherence measure.
        
        Physical Meaning:
            Computes a measure of phase coherence across the
            U(1)³ structure, indicating the degree of
            synchronization between the three phase components.
            
        Mathematical Foundation:
            Coherence = |Σ_a exp(iΘ_a)| / 3
            where the magnitude indicates coherence strength.
            
        Args:
            envelope (np.ndarray, optional): BVP envelope field. If None, uses current phase components.
            
        Returns:
            float: Phase coherence measure (0-1).
        """
        if envelope is not None:
            # Extract phases from envelope
            envelope_gpu = self._to_gpu(envelope)
            total_phase = self._cuda_angle(envelope_gpu)
            
            # Compute coherence from total phase
            coherence_sum = self._cuda_exp(1j * total_phase)
            coherence = self._cuda_abs(self._cuda_mean(coherence_sum))
        else:
            # Use current phase components
            coherence = self._phase_components.compute_phase_coherence()
            coherence_gpu = self._to_gpu(coherence)
            coherence = self._cuda_mean(coherence_gpu)  # Average over spatial points
        
        # Convert to CPU and return scalar
        return float(self._to_cpu(coherence))

