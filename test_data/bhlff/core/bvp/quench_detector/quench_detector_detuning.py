"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Detuning quench detection methods for quench detector.

This module provides detuning quench detection methods as a mixin class.
"""

import numpy as np
from typing import List, Dict, Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchDetectorDetuningMixin:
    """Mixin providing detuning quench detection methods."""
    
    def _detect_detuning_quenches(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect detuning quenches: |ω - ω_0| > Δω_q with advanced processing.
        
        Physical Meaning:
            Detects locations where the local frequency deviates
            significantly from the carrier frequency, indicating
            detuning quench events. Uses advanced frequency analysis
            and morphological operations for robust detection.
            
        Mathematical Foundation:
            Computes local frequency using phase evolution:
            ω_local = |dφ/dt| / dt
            Detuning = |ω_local - ω_0|
            Applies same morphological operations as amplitude quenches.
            
        Args:
            envelope (np.ndarray): 7D envelope field.
            
        Returns:
            List[Dict[str, Any]]: List of detuning quench events with
                enhanced characteristics.
        """
        quenches = []
        
        # Compute local frequency from phase evolution
        if envelope.shape[-1] > 1:  # Need at least 2 time slices
            local_frequency = self.characteristics.compute_local_frequency(envelope)
            
            # Detuning from carrier frequency
            detuning = np.abs(local_frequency - self.carrier_frequency)
            
            # Find locations exceeding detuning threshold
            quench_mask = detuning > self.detuning_threshold
            
            if np.any(quench_mask):
                # Apply morphological operations to filter noise
                quench_mask = self.morphology.apply_morphological_operations(
                    quench_mask
                )
                
                # Find connected components
                quench_components = self.morphology.find_connected_components(
                    quench_mask
                )
                
                # Process each component
                for component_id, component_mask in quench_components.items():
                    if np.sum(component_mask) < self.config.get("min_quench_size", 5):
                        continue  # Skip small components
                    
                    # Compute component characteristics
                    center = self.characteristics.compute_center_of_mass(component_mask)
                    strength = self.characteristics.compute_detuning_strength(
                        component_mask, detuning
                    )
                    size = np.sum(component_mask)
                    
                    quenches.append(
                        {
                            "location": center,
                            "type": "detuning",
                            "strength": float(strength),
                            "threshold": self.detuning_threshold,
                            "size": int(size),
                            "component_id": component_id,
                        }
                    )
        
        return quenches
    
    def _detect_detuning_quenches_cuda(self, envelope_gpu) -> List[Dict[str, Any]]:
        """Detect detuning quenches using CUDA acceleration."""
        quenches = []
        
        # Compute local frequency from phase evolution
        if envelope_gpu.shape[-1] > 1:  # Need at least 2 time slices
            local_frequency = self.characteristics.compute_local_frequency_cuda(
                envelope_gpu
            )
            
            # Detuning from carrier frequency
            detuning = cp.abs(local_frequency - self.carrier_frequency)
            
            # Find locations exceeding detuning threshold
            quench_mask = detuning > self.detuning_threshold
            
            if cp.any(quench_mask):
                # Apply morphological operations to filter noise
                quench_mask = self.morphology.apply_morphological_operations_cuda(
                    quench_mask
                )
                
                # Find connected components
                quench_components = self.morphology.find_connected_components_cuda(
                    quench_mask
                )
                
                # Process each component
                for component_id, component_mask in quench_components.items():
                    # Convert CuPy array to numpy for size check
                    component_mask_cpu = (
                        cp.asnumpy(component_mask)
                        if hasattr(component_mask, "get")
                        else component_mask
                    )
                    size = np.sum(component_mask_cpu)
                    
                    if size < self.config.get("min_quench_size", 5):
                        continue  # Skip small components
                    
                    # Compute component characteristics
                    center = self.characteristics.compute_center_of_mass_cuda(
                        component_mask
                    )
                    strength = self.characteristics.compute_detuning_strength_cuda(
                        component_mask, detuning
                    )
                    
                    quenches.append(
                        {
                            "location": center,
                            "type": "detuning",
                            "strength": float(strength),
                            "threshold": self.detuning_threshold,
                            "size": int(size),
                            "component_id": component_id,
                        }
                    )
        
        # Cleanup GPU memory
        if "local_frequency" in locals():
            del local_frequency
        if "detuning" in locals():
            del detuning
        if "quench_mask" in locals():
            del quench_mask
        if "quench_components" in locals():
            del quench_components
        
        return quenches

