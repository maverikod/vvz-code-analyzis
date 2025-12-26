"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data structures for ABCD model.

This module defines data structures for resonator layers and system modes
in the ABCD transmission matrix model.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ResonatorLayer:
    """
    Single resonator layer in the chain.

    Physical Meaning:
        Represents a single resonator layer with specific material
        properties and geometry that contribute to the overall
        system transmission characteristics.
    """

    radius: float
    thickness: float
    contrast: float
    memory_gamma: float = 0.0
    memory_tau: float = 1.0
    material_params: Optional[Dict[str, Any]] = None


@dataclass
class SystemMode:
    """
    System resonance mode.

    Physical Meaning:
        Represents a resonance mode of the entire resonator chain,
        characterized by its frequency, quality factor, and coupling
        properties with other modes.
    """

    frequency: float
    quality_factor: float
    amplitude: float
    phase: float
    mode_index: int
    coupling_strength: float = 0.0

