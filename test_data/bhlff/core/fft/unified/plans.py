"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

FFT planning helpers for unified spectral operations.

Physical Meaning:
    Provides lightweight plan descriptors for FFT execution. NumPy/CuPy manage
    runtime planning internally; we keep symbolic entries for introspection.
"""

from typing import Dict


def setup_fft_plans() -> Dict[str, str]:
    """
    Setup FFT plan descriptors.

    Returns:
        Dict[str, str]: Plan descriptor map.
    """
    return {
        "forward": "fftn_norm_ortho",
        "inverse": "ifftn_norm_ortho",
    }
