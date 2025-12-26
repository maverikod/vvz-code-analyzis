"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Interface facade implementation.

This module provides the main facade class for BVP interface,
coordinating all interface components and providing a unified
interface to the BVP framework.

Theoretical Background:
    The BVP interface facade serves as the main entry point for
    all interface operations, coordinating tail, transition zone,
    and core interfaces.

Example:
    >>> interface = BVPInterface(bvp_core)
    >>> tail_data = interface.interface_with_tail(envelope)
    >>> transition_data = interface.interface_with_transition_zone(envelope)
    >>> core_data = interface.interface_with_core(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_core.bvp_core_facade_impl import BVPCoreFacade as BVPCore
from .tail_interface import TailInterface
from .transition_interface import TransitionInterface
from .core_interface import CoreInterface


class BVPInterface:
    """
    Main facade for BVP interface operations.

    Physical Meaning:
        Provides the main interface between BVP and other system
        components, coordinating all interface operations and
        providing a unified interface to the BVP framework.

    Mathematical Foundation:
        Coordinates interface functions for:
        1. Tail interface: Provides Y(ω), {ω_n,Q_n}, R, T
        2. Transition zone interface: Provides Y_tr(ω,|A|), J_EM(ω;A)
        3. Core interface: Provides c_i^eff(A,∇A), boundary conditions
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize BVP interface facade.

        Physical Meaning:
            Sets up the interface facade with the BVP core module,
            establishing connections to all system components.

        Args:
            bvp_core (BVPCore): BVP core module instance.
        """
        self.bvp_core = bvp_core
        self.domain_7d = bvp_core.domain_7d
        self.config = bvp_core.config

        # Initialize interface components
        self.tail_interface = TailInterface(bvp_core)
        self.transition_interface = TransitionInterface(bvp_core)
        self.core_interface = CoreInterface(bvp_core)

    def interface_with_tail(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Interface BVP with tail resonators.

        Physical Meaning:
            Provides the necessary data for tail resonator calculations
            through the tail interface component.

        Args:
            envelope (np.ndarray): 7D envelope field at boundaries.

        Returns:
            Dict[str, Any]: Tail interface data.
        """
        return self.tail_interface.interface_with_tail(envelope)

    def interface_with_transition_zone(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Interface BVP with transition zone.

        Physical Meaning:
            Provides the necessary data for transition zone calculations
            through the transition interface component.

        Args:
            envelope (np.ndarray): 7D envelope field.

        Returns:
            Dict[str, Any]: Transition zone interface data.
        """
        return self.transition_interface.interface_with_transition_zone(envelope)

    def interface_with_core(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Interface BVP with core.

        Physical Meaning:
            Provides the necessary data for core calculations
            through the core interface component.

        Args:
            envelope (np.ndarray): 7D envelope field.

        Returns:
            Dict[str, Any]: Core interface data.
        """
        return self.core_interface.interface_with_core(envelope)

    def get_tail_interface(self) -> TailInterface:
        """
        Get the tail interface component.

        Physical Meaning:
            Returns the tail interface component for direct access
            to tail-specific operations.

        Returns:
            TailInterface: Tail interface component.
        """
        return self.tail_interface

    def get_transition_interface(self) -> TransitionInterface:
        """
        Get the transition interface component.

        Physical Meaning:
            Returns the transition interface component for direct access
            to transition zone-specific operations.

        Returns:
            TransitionInterface: Transition interface component.
        """
        return self.transition_interface

    def get_core_interface(self) -> CoreInterface:
        """
        Get the core interface component.

        Physical Meaning:
            Returns the core interface component for direct access
            to core-specific operations.

        Returns:
            CoreInterface: Core interface component.
        """
        return self.core_interface
