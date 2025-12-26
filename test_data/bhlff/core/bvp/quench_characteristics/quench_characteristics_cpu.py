"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU computation methods for quench characteristics.

This module provides CPU-based computation methods as a mixin class.
"""

import numpy as np
from typing import Tuple


class QuenchCharacteristicsCPUMixin:
    """Mixin providing CPU computation methods."""
    
    def compute_center_of_mass(self, component_mask: np.ndarray) -> Tuple[float, ...]:
        """
        Compute center of mass for a quench component.
        
        Physical Meaning:
            Calculates the center of mass of a quench component,
            representing the effective location of the quench event
            in 7D space-time.
        
        Mathematical Foundation:
            Center of mass = Σ(r_i * w_i) / Σ(w_i)
            where r_i are coordinates and w_i are weights (amplitudes).
        
        Args:
            component_mask (np.ndarray): Binary mask of component.
        
        Returns:
            Tuple[float, ...]: 7D coordinates of center of mass.
        """
        # Get coordinates of component points
        coords = np.where(component_mask)
        
        if len(coords[0]) == 0:
            return (0.0,) * 7
        
        # Compute center of mass (simple average for now)
        center = []
        for axis in range(7):
            center.append(float(np.mean(coords[axis])))
        
        return tuple(center)
    
    def compute_quench_strength(
        self, component_mask: np.ndarray, amplitude: np.ndarray
    ) -> float:
        """
        Compute quench strength for a component.
        
        Physical Meaning:
            Calculates the strength of a quench event based on
            the maximum amplitude within the component region.
        
        Mathematical Foundation:
            Quench strength = max(|A|) within component
            This represents the peak field strength in the quench region.
        
        Args:
            component_mask (np.ndarray): Binary mask of component.
            amplitude (np.ndarray): Amplitude field.
        
        Returns:
            float: Quench strength.
        """
        # Get amplitudes within component
        component_amplitudes = amplitude[component_mask]
        
        if len(component_amplitudes) == 0:
            return 0.0
        
        # Return maximum amplitude as quench strength
        return float(np.max(component_amplitudes))
    
    def compute_local_frequency(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute local frequency from phase evolution.
        
        Physical Meaning:
            Calculates the local frequency at each point in 7D space-time
            by analyzing the phase evolution of the envelope field.
            This represents the instantaneous frequency of the BVP field.
        
        Mathematical Foundation:
            ω_local = |dφ/dt| / dt
            where φ is the phase of the envelope and dt is the time step.
            Uses finite differences to approximate the derivative.
        
        Args:
            envelope (np.ndarray): 7D envelope field.
        
        Returns:
            np.ndarray: Local frequency field with same shape as envelope.
        """
        # Extract phase
        phase = np.angle(envelope)
        
        # Compute phase difference along time axis
        if envelope.shape[-1] > 1:
            phase_diff = np.diff(phase, axis=-1)
            
            # Get time step
            dt = self.domain_7d.temporal_config.dt
            
            # Compute local frequency (avoid division by zero)
            local_frequency = np.abs(phase_diff) / (dt + 1e-12)
            
            # Pad to match original shape
            local_frequency = np.pad(
                local_frequency,
                [(0, 0)] * (local_frequency.ndim - 1) + [(0, 1)],
                mode="edge",
            )
        else:
            # Single time slice - use zero frequency
            local_frequency = np.zeros_like(phase)
        
        return local_frequency
    
    def compute_detuning_strength(
        self, component_mask: np.ndarray, detuning: np.ndarray
    ) -> float:
        """
        Compute detuning strength for a component.
        
        Physical Meaning:
            Calculates the strength of a detuning quench event based on
            the maximum detuning within the component region.
        
        Mathematical Foundation:
            Detuning strength = max(|ω_local - ω_0|) within component
            This represents the peak frequency deviation in the quench region.
        
        Args:
            component_mask (np.ndarray): Binary mask of component.
            detuning (np.ndarray): Detuning field.
        
        Returns:
            float: Detuning strength.
        """
        # Get detuning values within component
        component_detuning = detuning[component_mask]
        
        if len(component_detuning) == 0:
            return 0.0
        
        # Return maximum detuning as quench strength
        return float(np.max(component_detuning))
    
    def compute_7d_gradient_magnitude(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute 7D gradient magnitude of envelope field.
        
        Physical Meaning:
            Calculates the magnitude of the gradient in all 7 dimensions
            (3 spatial + 3 phase + 1 temporal), representing the rate
            of change of the envelope field in 7D space-time.
        
        Mathematical Foundation:
            ∇A = (∂A/∂x, ∂A/∂y, ∂A/∂z, ∂A/∂φ₁, ∂A/∂φ₂, ∂A/∂φ₃, ∂A/∂t)
            |∇A| = √(Σ|∂A/∂xᵢ|²)
            Uses finite differences to approximate partial derivatives.
        
        Args:
            envelope (np.ndarray): 7D envelope field.
        
        Returns:
            np.ndarray: Gradient magnitude field with same shape as envelope.
        """
        # Get differentials for all 7 dimensions
        differentials = self.domain_7d.get_differentials()
        
        # Compute gradients in all 7 dimensions
        gradients = []
        
        # Spatial gradients (x, y, z)
        for axis, dx in enumerate(
            [differentials["dx"], differentials["dy"], differentials["dz"]]
        ):
            grad = np.gradient(envelope, dx, axis=axis)
            gradients.append(grad)
        
        # Phase gradients (φ₁, φ₂, φ₃)
        for axis, dphi in enumerate(
            [differentials["dphi_1"], differentials["dphi_2"], differentials["dphi_3"]]
        ):
            grad = np.gradient(envelope, dphi, axis=axis + 3)
            gradients.append(grad)
        
        # Temporal gradient (t)
        if envelope.shape[-1] > 1:
            dt = differentials.get("dt", 1.0)
            grad_t = np.gradient(envelope, dt, axis=-1)
            gradients.append(grad_t)
        else:
            # Single time slice - zero temporal gradient
            grad_t = np.zeros_like(envelope)
            gradients.append(grad_t)
        
        # Compute gradient magnitude
        grad_magnitude = np.sqrt(sum(np.abs(grad) ** 2 for grad in gradients))
        
        return grad_magnitude
    
    def compute_gradient_strength(
        self, component_mask: np.ndarray, gradient_magnitude: np.ndarray
    ) -> float:
        """
        Compute gradient strength for a component.
        
        Physical Meaning:
            Calculates the strength of a gradient quench event based on
            the maximum gradient magnitude within the component region.
        
        Mathematical Foundation:
            Gradient strength = max(|∇A|) within component
            This represents the peak gradient magnitude in the quench region.
        
        Args:
            component_mask (np.ndarray): Binary mask of component.
            gradient_magnitude (np.ndarray): Gradient magnitude field.
        
        Returns:
            float: Gradient strength.
        """
        # Get gradient magnitudes within component
        component_gradients = gradient_magnitude[component_mask]
        
        if len(component_gradients) == 0:
            return 0.0
        
        # Return maximum gradient magnitude as quench strength
        return float(np.max(component_gradients))

