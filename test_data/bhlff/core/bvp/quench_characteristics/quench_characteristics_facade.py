"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for quench characteristics.

This module provides the main QuenchCharacteristics facade class that
coordinates all quench characteristics components.
"""

from .quench_characteristics_base import QuenchCharacteristicsBase
from .quench_characteristics_cpu import QuenchCharacteristicsCPUMixin
from .quench_characteristics_cuda import QuenchCharacteristicsCUDAMixin


class QuenchCharacteristics(
    QuenchCharacteristicsBase,
    QuenchCharacteristicsCPUMixin,
    QuenchCharacteristicsCUDAMixin
):
    """
    Facade class for quench characteristics with all mixins.
    
    Physical Meaning:
        Computes various characteristics of quench events including
        center of mass, strength measures, and local frequency
        analysis to provide comprehensive quench event information.
    """
    pass

