"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Gradient computation for streamlines.

This module provides gradient computation functionality.
"""

import numpy as np
from typing import Any


class GradientComputer:
    """Compute field gradients and phase gradients."""
    
    def __init__(self, domain: "Domain"):
        """Initialize gradient computer."""
        self.domain = domain
    
    def compute_phase_gradient(self, phase: np.ndarray) -> np.ndarray:
        """
        Compute phase gradient field.
        
        Physical Meaning:
            Computes the gradient of the phase field,
            representing the local direction of phase
            flow and its magnitude.
        
        Mathematical Foundation:
            ∇φ = (∂φ/∂x, ∂φ/∂y, ∂φ/∂z)
        
        Args:
            phase (np.ndarray): Phase field
        
        Returns:
            np.ndarray: Phase gradient field
        """
        if len(phase.shape) == 3:
            # 3D gradient
            grad_x = np.gradient(phase, axis=0)
            grad_y = np.gradient(phase, axis=1)
            grad_z = np.gradient(phase, axis=2)
            gradient = np.stack([grad_x, grad_y, grad_z], axis=-1)
        elif len(phase.shape) == 2:
            # 2D gradient
            grad_x = np.gradient(phase, axis=0)
            grad_y = np.gradient(phase, axis=1)
            gradient = np.stack([grad_x, grad_y], axis=-1)
        else:
            # 1D gradient
            gradient = np.gradient(phase)
            gradient = np.expand_dims(gradient, axis=-1)
        
        return gradient
    
    def compute_field_gradients(self, field: np.ndarray) -> np.ndarray:
        """
        Compute field gradients.
        
        Physical Meaning:
            Computes the gradient of the field in all
            spatial dimensions.
        
        Args:
            field (np.ndarray): Input field
        
        Returns:
            np.ndarray: Field gradients
        """
        if len(field.shape) == 3:
            # 3D gradient
            grad_x = np.gradient(field, axis=0)
            grad_y = np.gradient(field, axis=1)
            grad_z = np.gradient(field, axis=2)
            gradients = np.stack([grad_x, grad_y, grad_z], axis=-1)
        elif len(field.shape) == 2:
            # 2D gradient
            grad_x = np.gradient(field, axis=0)
            grad_y = np.gradient(field, axis=1)
            gradients = np.stack([grad_x, grad_y], axis=-1)
        else:
            # 1D gradient
            gradients = np.gradient(field)
            gradients = np.expand_dims(gradients, axis=-1)
        
        return gradients
    
    def compute_divergence(self, gradients: np.ndarray) -> np.ndarray:
        """
        Compute divergence of gradient field.
        
        Physical Meaning:
            Computes the divergence of the gradient field,
            representing sources and sinks in the flow.
        
        Mathematical Foundation:
            ∇·v = ∂v_x/∂x + ∂v_y/∂y + ∂v_z/∂z
        
        Args:
            gradients (np.ndarray): Gradient field
        
        Returns:
            np.ndarray: Divergence field
        """
        if gradients.shape[-1] == 3:
            # 3D divergence
            div_x = np.gradient(gradients[..., 0], axis=0)
            div_y = np.gradient(gradients[..., 1], axis=1)
            div_z = np.gradient(gradients[..., 2], axis=2)
            divergence = div_x + div_y + div_z
        elif gradients.shape[-1] == 2:
            # 2D divergence
            div_x = np.gradient(gradients[..., 0], axis=0)
            div_y = np.gradient(gradients[..., 1], axis=1)
            divergence = div_x + div_y
        else:
            # 1D divergence
            divergence = np.gradient(gradients[..., 0], axis=0)
        
        return divergence
    
    def compute_curl(self, gradients: np.ndarray) -> np.ndarray:
        """
        Compute curl of gradient field.
        
        Physical Meaning:
            Computes the curl of the gradient field,
            representing rotational flow patterns.
        
        Mathematical Foundation:
            ∇×v = (∂v_z/∂y - ∂v_y/∂z, ∂v_x/∂z - ∂v_z/∂x, ∂v_y/∂x - ∂v_x/∂y)
        
        Args:
            gradients (np.ndarray): Gradient field
        
        Returns:
            np.ndarray: Curl field
        """
        if gradients.shape[-1] == 3:
            # 3D curl
            curl_x = np.gradient(gradients[..., 2], axis=1) - np.gradient(
                gradients[..., 1], axis=2
            )
            curl_y = np.gradient(gradients[..., 0], axis=2) - np.gradient(
                gradients[..., 2], axis=0
            )
            curl_z = np.gradient(gradients[..., 1], axis=0) - np.gradient(
                gradients[..., 0], axis=1
            )
            curl = np.stack([curl_x, curl_y, curl_z], axis=-1)
        elif gradients.shape[-1] == 2:
            # 2D curl (scalar)
            curl = np.gradient(gradients[..., 1], axis=0) - np.gradient(
                gradients[..., 0], axis=1
            )
            curl = np.expand_dims(curl, axis=-1)
        else:
            # 1D curl (zero)
            curl = np.zeros_like(gradients)
        
        return curl

