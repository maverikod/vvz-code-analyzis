"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for multi-soliton optimization.

This module provides the base MultiSolitonOptimizationBase class with common
initialization and main optimization methods.
"""

from typing import Dict, Any, List
import logging

from ..base import SolitonAnalysisBase
from ..multi_soliton_core import MultiSolitonCore
from ..multi_soliton_validation import MultiSolitonValidation


class MultiSolitonOptimizationBase(SolitonAnalysisBase):
    """
    Base class for multi-soliton optimization.
    
    Physical Meaning:
        Provides base functionality for multi-soliton optimization including
        parameter optimization, solution finding, and convergence analysis
        using 7D BVP theory.
        
    Mathematical Foundation:
        Optimizes multi-soliton parameters using complete 7D BVP theory
        with multiple initial guesses and advanced convergence criteria.
    """
    
    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton optimization."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)
        
        # Initialize core functionality
        self.core = MultiSolitonCore(system, nonlinear_params)
        self.validator = MultiSolitonValidation(system, nonlinear_params)
    
    def find_multi_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find multi-soliton solutions using full 7D BVP theory.
        
        Physical Meaning:
            Finds multi-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and interaction
            potentials between solitons.
            
        Returns:
            List[Dict[str, Any]]: Multi-soliton solutions with full
            physical parameters and interaction analysis.
        """
        multi_solitons = []
        
        try:
            # Find two-soliton solution with full optimization
            two_soliton = self.find_two_soliton_solutions()
            if two_soliton:
                multi_solitons.extend(two_soliton)
            
            # Find three-soliton solution with full optimization
            three_soliton = self.find_three_soliton_solutions()
            if three_soliton:
                multi_solitons.extend(three_soliton)
            
            return multi_solitons
        
        except Exception as e:
            self.logger.error(f"Multi-soliton solutions finding failed: {e}")
            return []

