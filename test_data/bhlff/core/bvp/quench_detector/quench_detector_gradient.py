"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Gradient quench detection methods for quench detector.

This module provides gradient quench detection methods as a mixin class.
"""

import numpy as np
from typing import List, Dict, Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class QuenchDetectorGradientMixin:
    """Mixin providing gradient quench detection methods."""
    
    def _detect_gradient_quenches(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect gradient quenches: |∇A| > |∇A_q| with advanced processing.
        
        Physical Meaning:
            Detects locations where the envelope gradient exceeds
            the gradient threshold, indicating potential quench events
            due to high spatial/phase gradients. Uses 7D gradient computation
            and morphological operations for robust detection.
            
        Mathematical Foundation:
            Computes 7D gradient: ∇A = (∂A/∂x, ∂A/∂y, ∂A/∂z, ∂A/∂φ₁, ∂A/∂φ₂, ∂A/∂φ₃, ∂A/∂t)
            Gradient magnitude: |∇A| = √(Σ|∂A/∂xᵢ|²)
            Applies same morphological operations as other quench types.
            
        Args:
            envelope (np.ndarray): 7D envelope field.
            
        Returns:
            List[Dict[str, Any]]: List of gradient quench events with
                enhanced characteristics.
        """
        quenches = []
        
        # Compute 7D gradient
        gradient_magnitude = self.characteristics.compute_7d_gradient_magnitude(
            envelope
        )
        
        # Find locations exceeding gradient threshold
        quench_mask = gradient_magnitude > self.gradient_threshold
        
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
                strength = self.characteristics.compute_gradient_strength(
                    component_mask, gradient_magnitude
                )
                size = np.sum(component_mask)
                
                quenches.append(
                    {
                        "location": center,
                        "type": "gradient",
                        "strength": float(strength),
                        "threshold": self.gradient_threshold,
                        "size": int(size),
                        "component_id": component_id,
                    }
                )
        
        return quenches
    
    def _detect_gradient_quenches_cuda(self, envelope_gpu) -> List[Dict[str, Any]]:
        """Detect gradient quenches using CUDA acceleration."""
        quenches = []
        
        # Compute 7D gradient on GPU
        gradient_magnitude = self.characteristics.compute_7d_gradient_magnitude_cuda(
            envelope_gpu
        )
        
        # Find locations exceeding gradient threshold
        quench_mask = gradient_magnitude > self.gradient_threshold
        
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
                strength = self.characteristics.compute_gradient_strength_cuda(
                    component_mask, gradient_magnitude
                )
                
                quenches.append(
                    {
                        "location": center,
                        "type": "gradient",
                        "strength": float(strength),
                        "threshold": self.gradient_threshold,
                        "size": int(size),
                        "component_id": component_id,
                    }
                )
        
        # Cleanup GPU memory
        if "gradient_magnitude" in locals():
            del gradient_magnitude
        if "quench_mask" in locals():
            del quench_mask
        if "quench_components" in locals():
            del quench_components
        
        return quenches

