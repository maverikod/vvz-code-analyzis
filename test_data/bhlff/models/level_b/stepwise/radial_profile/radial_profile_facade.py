"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for radial profile computation.

This module provides the main RadialProfileComputer facade class that
coordinates all radial profile computation components.
"""

from .radial_profile_base import RadialProfileComputerBase


class RadialProfileComputer(RadialProfileComputerBase):
    """
    Facade class for radial profile computation with CUDA acceleration.
    
    Physical Meaning:
        Computes radial profiles by averaging field values over spherical
        shells, providing the basis for analyzing decay behavior and
        layer structure in the phase field.
        
    Mathematical Foundation:
        For a field a(x), the radial profile A(r) is computed as:
        A(r) = (1/V_r) ∫_{|x-c|=r} |a(x)| dS
        where V_r is the volume of the spherical shell at radius r.
    """
    pass

