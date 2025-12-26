"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Unified spectral operations shim module.

This file re-exports the facade class from the modular unified FFT package to
preserve backward compatibility while keeping this file well below the 400-line
limit required by project standards.
"""

from bhlff.core.fft.unified import UnifiedSpectralOperations  # noqa: F401
