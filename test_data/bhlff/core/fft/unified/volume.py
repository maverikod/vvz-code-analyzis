"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Volume element computation for physics normalization in 7D FFTs.
"""

from typing import Tuple
import numpy as np


def compute_volume_element(domain_shape: Tuple[int, ...]) -> float:
    """
    Compute 7D volume element Δ^7 for physics normalization.

    Args:
        domain_shape: Shape of the computational domain.

    Returns:
        float: Volume element.
    """
    dx = 1.0 / domain_shape[0] if len(domain_shape) > 0 else 1.0
    dy = 1.0 / domain_shape[1] if len(domain_shape) > 1 else dx
    dz = 1.0 / domain_shape[2] if len(domain_shape) > 2 else dy
    dphi1 = 2 * np.pi / domain_shape[3] if len(domain_shape) > 3 else 1.0
    dphi2 = 2 * np.pi / domain_shape[4] if len(domain_shape) > 4 else 1.0
    dphi3 = 2 * np.pi / domain_shape[5] if len(domain_shape) > 5 else 1.0
    dt = 1.0 / domain_shape[6] if len(domain_shape) > 6 else 1.0
    return dx * dy * dz * dphi1 * dphi2 * dphi3 * dt
