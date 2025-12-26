"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase transitions facade for Level F models.

This module provides a facade interface for phase transitions,
delegating to specialized modules for different aspects of
phase transition analysis.

Theoretical Background:
    Phase transitions in multi-particle systems are described by
    Landau theory adapted for topological systems. Order parameters
    characterize different phases, and critical points mark transitions
    between phases.

Example:
    >>> transitions = PhaseTransitions(system)
    >>> phase_diagram = transitions.parameter_sweep('temperature', values)
    >>> critical_points = transitions.identify_critical_points(phase_diagram)
"""

from .transitions.phase_transitions_core import PhaseTransitions

# Re-export the main class for backward compatibility
__all__ = ["PhaseTransitions"]
