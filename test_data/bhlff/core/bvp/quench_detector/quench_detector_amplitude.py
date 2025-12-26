"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Amplitude quench detection methods for quench detector.

This module provides amplitude quench detection methods as a mixin class.
"""

import numpy as np
from typing import List, Dict, Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchDetectorAmplitudeMixin:
    """Mixin providing amplitude quench detection methods."""
    
    def _detect_amplitude_quenches(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect amplitude quenches: |A| > |A_q| with advanced processing.
        
        Physical Meaning:
            Detects locations where the envelope amplitude exceeds
            the amplitude threshold, indicating potential quench events
            due to high field strength. Uses morphological operations
            to filter noise and find connected components.
            
        Mathematical Foundation:
            Applies morphological operations to filter noise:
            - Binary opening: removes small noise components
            - Binary closing: fills small gaps in quench regions
            - Connected component analysis: groups nearby quench events
            
        Args:
            envelope (np.ndarray): 7D envelope field.
            
        Returns:
            List[Dict[str, Any]]: List of amplitude quench events with
                enhanced characteristics including size and center of mass.
        """
        quenches = []
        
        # Compute amplitude
        amplitude = np.abs(envelope)
        
        # Find locations exceeding threshold
        quench_mask = amplitude > self.amplitude_threshold
        
        if np.any(quench_mask):
            # Apply morphological operations to filter noise
            quench_mask = self.morphology.apply_morphological_operations(quench_mask)
            
            # Find connected components
            quench_components = self.morphology.find_connected_components(quench_mask)
            
            # Process each component
            for component_id, component_mask in quench_components.items():
                if np.sum(component_mask) < self.config.get("min_quench_size", 5):
                    continue  # Skip small components
                
                # Compute component characteristics
                center = self.characteristics.compute_center_of_mass(component_mask)
                strength = self.characteristics.compute_quench_strength(
                    component_mask, amplitude
                )
                size = np.sum(component_mask)
                
                quenches.append(
                    {
                        "location": center,
                        "type": "amplitude",
                        "strength": float(strength),
                        "threshold": self.amplitude_threshold,
                        "size": int(size),
                        "component_id": component_id,
                    }
                )
        
        return quenches
    
    def _detect_amplitude_quenches_cuda(self, envelope_gpu) -> List[Dict[str, Any]]:
        """Detect amplitude quenches using CUDA acceleration."""
        quenches = []
        
        # Compute amplitude on GPU
        amplitude = cp.abs(envelope_gpu)
        
        # Find locations exceeding threshold
        quench_mask = amplitude > self.amplitude_threshold
        
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
                
                # Use adaptive minimum size based on array size
                min_size = max(1, min(5, envelope_gpu.size // 1000))
                if size < min_size:
                    continue  # Skip small components
                
                # Compute component characteristics
                center = self.characteristics.compute_center_of_mass_cuda(
                    component_mask
                )
                strength = self.characteristics.compute_quench_strength_cuda(
                    component_mask, amplitude
                )
                
                quenches.append(
                    {
                        "location": center,
                        "type": "amplitude",
                        "strength": float(strength),
                        "threshold": self.amplitude_threshold,
                        "size": int(size),
                        "component_id": component_id,
                    }
                )
        
        # Cleanup GPU memory
        del amplitude, quench_mask
        if "quench_components" in locals():
            del quench_components
        
        return quenches

