"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced solver core facade for 7D BVP envelope equation.

This module provides a unified interface for advanced solving functionality,
delegating to specialized modules for different aspects of solving.
"""

from .advanced import SolverAdvancedCore

# Alias for backward compatibility
EnvelopeSolverCoreAdvanced = SolverAdvancedCore

__all__ = ["SolverAdvancedCore", "EnvelopeSolverCoreAdvanced"]
