"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimization advanced beating validation facade for Level C.

This module provides a unified interface for optimization-based beating validation,
delegating to specialized modules for different aspects of optimization.
"""

from .optimization import BeatingValidationOptimizationCore

# Alias for backward compatibility
BeatingValidationAdvancedOptimization = BeatingValidationOptimizationCore

__all__ = ["BeatingValidationOptimizationCore", "BeatingValidationAdvancedOptimization"]
