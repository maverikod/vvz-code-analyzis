"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power Balance Postulate package for BVP framework.

This package provides modular components for the Power Balance Postulate,
including flux computation, energy analysis, and radiation calculations.

Theoretical Background:
    Power balance is maintained at the external boundary through proper
    accounting of energy flows. The integral identity ensures conservation
    of energy in the BVP system.

Example:
    >>> from bhlff.core.bvp.postulates.power_balance import PowerBalancePostulate
    >>> postulate = PowerBalancePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

from .power_balance_postulate import PowerBalancePostulate
from .flux_computer import FluxComputer
from .energy_analyzer import EnergyAnalyzer
from .radiation_calculator import RadiationCalculator

__all__ = [
    "PowerBalancePostulate",
    "FluxComputer",
    "EnergyAnalyzer",
    "RadiationCalculator",
]
