"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for multi-soliton optimization.

This module provides the main MultiSolitonOptimization facade class that
coordinates all multi-soliton optimization components.
"""

from .multi_soliton_optimization_base import MultiSolitonOptimizationBase
from .multi_soliton_optimization_two import MultiSolitonOptimizationTwoMixin
from .multi_soliton_optimization_three import MultiSolitonOptimizationThreeMixin
from .multi_soliton_optimization_resonator import MultiSolitonOptimizationResonatorMixin
from .multi_soliton_optimization_computations import MultiSolitonOptimizationComputationsMixin


class MultiSolitonOptimization(
    MultiSolitonOptimizationBase,
    MultiSolitonOptimizationTwoMixin,
    MultiSolitonOptimizationThreeMixin,
    MultiSolitonOptimizationResonatorMixin,
    MultiSolitonOptimizationComputationsMixin
):
    """
    Facade class for multi-soliton optimization with all mixins.
    
    Physical Meaning:
        Implements multi-soliton optimization including parameter optimization,
        solution finding, and convergence analysis using 7D BVP theory.
        
    Mathematical Foundation:
        Optimizes multi-soliton parameters using complete 7D BVP theory
        with multiple initial guesses and advanced convergence criteria.
    """
    pass

