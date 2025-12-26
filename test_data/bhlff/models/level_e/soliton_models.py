"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton models for Level E experiments in 7D phase field theory.

This module provides the main interface for soliton models, importing
from specialized modules for core functionality and specific implementations.

Theoretical Background:
    Solitons are stable localized field configurations that minimize
    the energy functional while preserving topological charge. In the
    7D theory, they represent baryons and other particle-like structures
    through U(1)^3 phase patterns on the VBP substrate with controlled
    winding over φ-coordinates.

Mathematical Foundation:
    Implements 7D phase field configuration Θ(x,φ,t) ∈ T^3_φ with
    topological charge B = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ) and WZW
    term for baryon number conservation. The classical SU(3) field
    configuration is a 4D pedagogical limit, not the core 7D construction.

Example:
    >>> soliton = BaryonSoliton(domain, physics_params)
    >>> solution = soliton.find_soliton_solution(initial_guess)
"""

# Import core soliton functionality
from .soliton_core import SolitonModel
from .soliton_optimization import ConvergenceError

# Import specific soliton implementations
from .soliton_implementations import BaryonSoliton, SkyrmionSoliton

# Import specialized modules
from .soliton_energy import SolitonEnergyCalculator
from .soliton_stability import SolitonStabilityAnalyzer
from .soliton_optimization import SolitonOptimizer

# Re-export for backward compatibility
__all__ = [
    "SolitonModel",
    "BaryonSoliton",
    "SkyrmionSoliton",
    "ConvergenceError",
    "SolitonEnergyCalculator",
    "SolitonStabilityAnalyzer",
    "SolitonOptimizer",
]
