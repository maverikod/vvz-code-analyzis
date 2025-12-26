"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transition zone interface implementation for BVP framework.

This module implements the interface between BVP and transition zone,
providing the necessary data transformations for transition zone calculations.

Theoretical Background:
    The transition zone interface provides the necessary data for transition
    zone calculations including nonlinear admittance Y_tr(ω,|A|), EM/weak
    current sources J_EM(ω;A), loss map χ''(|A|), and input admittance Y_in.

Example:
    >>> transition_interface = TransitionInterface(bvp_core)
    >>> transition_data = transition_interface.interface_with_transition_zone(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_core.bvp_core_facade_impl import BVPCoreFacade as BVPCore
from .tail_interface import TailInterface


class TransitionInterface:
    """
    Interface between BVP and transition zone.

    Physical Meaning:
        Provides the connection between BVP envelope and transition zone.
        This interface implements the data transformations required for
        integrating BVP with transition zone calculations.

    Mathematical Foundation:
        Implements interface functions for transition zone:
        1. Nonlinear admittance Y_tr(ω,|A|) for transition zone analysis
        2. EM/weak current sources J_EM(ω;A) generated from envelope
        3. Loss map χ''(|A|) for quench analysis
        4. Input admittance Y_in from tail interface
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize transition zone interface.

        Physical Meaning:
            Sets up the interface with the BVP core module for
            transition zone calculations.

        Args:
            bvp_core (BVPCore): BVP core module instance.
        """
        self.bvp_core = bvp_core
        self.domain_7d = getattr(bvp_core, "domain_7d", None) or bvp_core.domain
        self.config = bvp_core.config
        self.tail_interface = TailInterface(bvp_core)

    def interface_with_transition_zone(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Interface BVP with transition zone.

        Physical Meaning:
            Provides the necessary data for transition zone calculations:
            - Nonlinear admittance Y_tr(ω,|A|) for transition zone analysis
            - EM/weak current sources J_EM(ω;A) generated from envelope
            - Loss map χ''(|A|) for quench analysis
            - Input admittance Y_in from tail interface

        Mathematical Foundation:
            Computes transition zone interface functions:
            - Y_tr(ω,|A|) = Y_0(ω) + Y_nl(|A|) - nonlinear admittance
            - J_EM(ω;A) = f(A,∇A) - EM current sources from envelope
            - χ''(|A|) = χ''_0 + χ''_nl(|A|) - loss map with quenches

        Args:
            envelope (np.ndarray): 7D envelope field.

        Returns:
            Dict[str, Any]: Transition zone interface data including:
                - nonlinear_admittance (np.ndarray): Y_tr(ω,|A|) response
                - em_current_sources (np.ndarray): J_EM(ω;A) current sources
                - loss_map (np.ndarray): χ''(|A|) loss distribution
                - input_admittance (np.ndarray): Y_in from tail
        """
        # Compute nonlinear admittance
        nonlinear_admittance = self._compute_nonlinear_admittance(envelope)

        # Compute EM current sources
        em_current_sources = self._compute_em_current_sources(envelope)

        # Compute loss map
        loss_map = self._compute_loss_map(envelope)

        # Get input admittance from tail interface
        tail_data = self.tail_interface.interface_with_tail(envelope)
        input_admittance = tail_data["admittance"]

        transition_data = {
            "nonlinear_admittance": nonlinear_admittance,
            "em_current_sources": em_current_sources,
            "loss_map": loss_map,
            "input_admittance": input_admittance,
        }

        return transition_data

    def _compute_nonlinear_admittance(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear admittance Y_tr(ω,|A|).

        Physical Meaning:
            Computes the nonlinear admittance that depends on both
            frequency and envelope amplitude, representing the
            transition zone response.

        Returns:
            np.ndarray: Nonlinear admittance Y_tr(ω,|A|).
        """
        # Base admittance
        base_admittance = np.ones_like(envelope)

        # Nonlinear correction based on amplitude
        amplitude = np.abs(envelope)
        nonlinear_correction = 1.0 + 0.1 * amplitude**2

        return base_admittance * nonlinear_correction

    def _compute_em_current_sources(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute EM current sources J_EM(ω;A).

        Physical Meaning:
            Computes the electromagnetic current sources generated
            from the BVP envelope, representing the coupling
            between BVP and EM fields.

        Returns:
            np.ndarray: EM current sources J_EM(ω;A).
        """
        # Current sources proportional to envelope amplitude and gradient
        amplitude = np.abs(envelope)

        # Compute gradient magnitude
        differentials = self.domain_7d.get_differentials()
        grad_x = np.gradient(envelope, differentials["dx"], axis=0)
        grad_y = np.gradient(envelope, differentials["dy"], axis=1)
        grad_z = np.gradient(envelope, differentials["dz"], axis=2)

        grad_magnitude = np.sqrt(
            np.abs(grad_x) ** 2 + np.abs(grad_y) ** 2 + np.abs(grad_z) ** 2
        )

        # Current sources
        current_sources = amplitude * grad_magnitude

        return current_sources

    def _compute_loss_map(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute loss map χ''(|A|).

        Physical Meaning:
            Computes the loss map that shows how losses depend
            on the envelope amplitude, including quench effects.

        Returns:
            np.ndarray: Loss map χ''(|A|).
        """
        # Base losses
        base_losses = 0.01 * np.ones_like(envelope)

        # Nonlinear losses (quenches)
        amplitude = np.abs(envelope)
        nonlinear_losses = 0.1 * amplitude**2

        return base_losses + nonlinear_losses
