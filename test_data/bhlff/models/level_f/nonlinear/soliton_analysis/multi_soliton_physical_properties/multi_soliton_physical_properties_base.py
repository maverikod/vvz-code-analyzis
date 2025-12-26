"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for multi-soliton physical properties.

This module provides the base MultiSolitonPhysicalPropertiesBase class with common
initialization and main computation methods.
"""

from typing import Dict, Any
import logging

from ..base import SolitonAnalysisBase


class MultiSolitonPhysicalPropertiesBase(SolitonAnalysisBase):
    """
    Base class for multi-soliton physical properties computation.
    
    Physical Meaning:
        Provides base functionality for physical properties computation
        including energy calculations, stability metrics, phase coherence,
        and 7D BVP specific properties for multi-soliton systems.
    """
    
    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton physical properties."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

