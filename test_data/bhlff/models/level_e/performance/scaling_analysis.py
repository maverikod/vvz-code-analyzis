"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scaling analysis facade for performance optimization.

This module provides a facade interface for comprehensive
scaling analysis functionality in 7D phase field theory
simulations.

Theoretical Background:
    Scaling analysis investigates the relationship between
    computational cost and problem size, providing insights
    into algorithmic efficiency and optimization opportunities.

Example:
    >>> analyzer = ScalingAnalyzer(config)
    >>> results = analyzer.analyze_scaling_behavior()
"""

from typing import Dict, Any
from .scaling import ScalingAnalyzer as CoreScalingAnalyzer


class ScalingAnalyzer:
    """
    Scaling analysis facade for computational efficiency.

    Physical Meaning:
        Provides a unified interface for comprehensive scaling
        analysis in 7D phase field simulations, including base
        scaling, performance scaling, and optimization analysis.

    Mathematical Foundation:
        Implements comprehensive scaling analysis through
        specialized modules for different aspects of scaling
        behavior.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scaling analyzer facade.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.core_analyzer = CoreScalingAnalyzer(config)

    def analyze_scaling_behavior(self) -> Dict[str, Any]:
        """Analyze comprehensive scaling behavior."""
        return self.core_analyzer.analyze_scaling_behavior()
