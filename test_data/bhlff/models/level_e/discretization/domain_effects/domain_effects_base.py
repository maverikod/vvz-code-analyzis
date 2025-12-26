"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for domain effects analyzer.

This module provides the base DomainEffectsAnalyzerBase class with common
initialization and setup methods.
"""

from typing import Dict, Any


class DomainEffectsAnalyzerBase:
    """
    Base class for domain effects analyzer.
    
    Physical Meaning:
        Provides base functionality for analyzing domain size effects
        in 7D phase field theory simulations.
    """
    
    def __init__(self, reference_config: Dict[str, Any]):
        """
        Initialize domain effects analyzer.
        
        Args:
            reference_config: Reference configuration for comparison
        """
        self.reference_config = reference_config
        self._setup_convergence_metrics()
    
    def _setup_convergence_metrics(self) -> None:
        """Setup metrics for convergence analysis."""
        self.convergence_metrics = [
            "power_law_exponent",
            "topological_charge",
            "energy",
            "quality_factor",
            "stability",
        ]

