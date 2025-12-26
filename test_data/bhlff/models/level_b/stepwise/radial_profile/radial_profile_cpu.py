"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU implementation for radial profile computation.

This module provides CPU-based radial profile computation methods.

Theoretical Background:
    Radial profiles A(r) are computed by averaging field values over
    spherical shells centered at defects, enabling analysis of decay
    behavior and layer structure in 7D space-time.

Example:
    >>> from .radial_profile_cpu import RadialProfileComputerCPU
    >>> cpu_computer = RadialProfileComputerCPU()
    >>> profile = cpu_computer._compute_cpu(field, center)
"""

import numpy as np
from typing import Dict, List
import logging


class RadialProfileComputerCPU:
    """
    CPU implementation for radial profile computation.
    
    Physical Meaning:
        Computes radial profiles using CPU operations, suitable for
        smaller fields or when CUDA is unavailable.
        
    Mathematical Foundation:
        For a field a(x), the radial profile A(r) is computed as:
        A(r) = (1/V_r) ∫_{|x-c|=r} |a(x)| dS
        where V_r is the volume of the spherical shell at radius r.
    """
    
    def __init__(self, logger: logging.Logger = None):
        """
        Initialize CPU radial profile computer.
        
        Args:
            logger (logging.Logger): Logger instance.
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def _compute_cpu(
        self, field: np.ndarray, center: List[float]
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile using CPU.
        
        Physical Meaning:
            Computes radial profile A(r) using CPU operations,
            suitable for smaller fields or when CUDA is unavailable.
            
        Args:
            field (np.ndarray): Field array.
            center (List[float]): Center coordinates [x, y, z].
                
        Returns:
            Dict[str, np.ndarray]: Radial profile with 'r' and 'A' arrays.
        """
        if len(field.shape) == 7:
            shape = field.shape[:3]
        else:
            shape = field.shape[:3]
        
        x = np.arange(shape[0])
        y = np.arange(shape[1])
        z = np.arange(shape[2])
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        distances = np.sqrt(
            (X - center[0]) ** 2 + (Y - center[1]) ** 2 + (Z - center[2]) ** 2
        )
        
        if len(field.shape) == 7:
            center_phi = field.shape[3] // 2
            center_t = field.shape[6] // 2
            amplitude = np.abs(
                field[:, :, :, center_phi, center_phi, center_phi, center_t]
            )
        else:
            amplitude = np.abs(field)
        
        r_max = np.max(distances)
        r_bins = np.linspace(0, r_max, min(100, int(r_max)))
        r_centers = (r_bins[:-1] + r_bins[1:]) / 2
        
        A_radial = []
        for i in range(len(r_bins) - 1):
            mask = (distances >= r_bins[i]) & (distances < r_bins[i + 1])
            if np.any(mask):
                A_radial.append(np.mean(amplitude[mask]))
            else:
                A_radial.append(0.0)
        
        return {"r": r_centers, "A": np.array(A_radial)}

