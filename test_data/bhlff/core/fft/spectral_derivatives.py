"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral derivatives module for 7D BHLFF Framework - Main facade.

This module provides the main facade for spectral derivative operations
for the 7D phase field theory, importing and organizing all derivative
components while maintaining the 1 class = 1 file principle.

Physical Meaning:
    Spectral derivatives implement mathematical differentiation operations
    in frequency space, providing efficient computation of derivatives
    for 7D phase field calculations with U(1)³ phase structure.

Mathematical Foundation:
    Implements spectral derivatives using the property that differentiation
    in real space corresponds to multiplication by ik in frequency space:
    - Gradient: ∇a → ik * â(k)
    - Divergence: ∇·a → ik · â(k)
    - Curl: ∇×a → ik × â(k)
    - Laplacian: Δa → -|k|² * â(k)

Example:
    >>> deriv = SpectralDerivatives(domain, precision="float64")
    >>> gradient = deriv.compute_gradient(field)
    >>> laplacian = deriv.compute_laplacian(field)
"""

# Import the main implementation
from .spectral_derivatives_impl import SpectralDerivatives

# Re-export for backward compatibility
__all__ = ["SpectralDerivatives"]
