"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade for solver core modules.

This module provides a unified interface for all solver core
functionality, delegating to specialized modules for different
aspects of solver core operations.
"""

from .solver_core_basic import EnvelopeSolverCoreBasic
from .solver_core_advanced import EnvelopeSolverCoreAdvanced

# Alias for backward compatibility
EnvelopeSolverCore7D = EnvelopeSolverCoreAdvanced

__all__ = [
    "EnvelopeSolverCoreBasic",
    "EnvelopeSolverCoreAdvanced",
    "EnvelopeSolverCore7D",
]
