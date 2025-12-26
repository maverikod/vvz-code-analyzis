"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Abstract time integrator base class with BVP framework integration.

This module provides the abstract base class for all time integrators
in the BHLFF framework with full BVP framework integration.

Physical Meaning:
    Time integrators implement numerical methods for advancing BVP envelope
    configurations in time, handling the temporal evolution of the system
    with quench detection and memory kernel support.

Mathematical Foundation:
    Implements various time integration schemes including explicit, implicit,
    and adaptive methods for solving time-dependent BVP envelope equations
    with memory kernel and quench events.

Example:
    >>> integrator = BVPModulationIntegrator(domain, config, bvp_core)
    >>> envelope_next = integrator.step(envelope_current, dt)
    >>> quenches = integrator.detect_quenches(envelope_next)
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any, Optional

from bhlff.core.domain import Domain
from bhlff.core.bvp import BVPCore, QuenchDetector


class TimeIntegrator(ABC):
    """
    Abstract base class for time integrators with BVP framework integration.

    Physical Meaning:
        Provides the fundamental interface for all time integrators in the
        7D phase field theory, representing numerical methods for temporal
        evolution of BVP envelope configurations with quench detection.

    Mathematical Foundation:
        Time integrators solve time-dependent BVP envelope equations:
        ∂a/∂t = F(a, t) with memory kernel and quench events
        where F(a, t) represents the right-hand side of the BVP evolution equation.

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): Integrator configuration.
        bvp_core (Optional[BVPCore]): BVP framework integration.
        quench_detector (Optional[QuenchDetector]): Quench detection system.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], bvp_core: Optional[BVPCore] = None
    ) -> None:
        """
        Initialize time integrator with BVP framework integration.

        Physical Meaning:
            Sets up the time integrator with computational domain and
            configuration parameters for temporal evolution,
            with optional BVP framework integration.

        Args:
            domain (Domain): Computational domain for the integrator.
            config (Dict[str, Any]): Integrator configuration parameters.
            bvp_core (Optional[BVPCore]): BVP framework integration.
        """
        self.domain = domain
        self.config = config
        self.bvp_core = bvp_core
        self.quench_detector: Optional[QuenchDetector] = None

        if self.bvp_core is not None:
            quench_config = config.get("quench_detection", {})
            self.quench_detector = QuenchDetector(quench_config)

    @abstractmethod
    def step(self, field: np.ndarray, dt: float) -> np.ndarray:
        """
        Perform one time step.

        Physical Meaning:
            Advances the phase field configuration by one time step,
            computing the temporal evolution of the field.

        Mathematical Foundation:
            Solves ∂a/∂t = F(a, t) for one time step:
            a(t + dt) = a(t) + ∫[t to t+dt] F(a, τ) dτ

        Args:
            field (np.ndarray): Current field configuration a(t).
            dt (float): Time step size.

        Returns:
            np.ndarray: Updated field configuration a(t + dt).

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement step method")

    @abstractmethod
    def get_integrator_type(self) -> str:
        """
        Get the integrator type.

        Physical Meaning:
            Returns the type of time integrator being used.

        Returns:
            str: Integrator type.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError(
            "Subclasses must implement get_integrator_type method"
        )

    def get_domain(self) -> Domain:
        """
        Get the computational domain.

        Physical Meaning:
            Returns the computational domain for the integrator.

        Returns:
            Domain: Computational domain.
        """
        return self.domain

    def get_config(self) -> Dict[str, Any]:
        """
        Get the integrator configuration.

        Physical Meaning:
            Returns the configuration parameters for the integrator.

        Returns:
            Dict[str, Any]: Integrator configuration.
        """
        return self.config.copy()

    def detect_quenches(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Detect quench events in BVP envelope.

        Physical Meaning:
            Detects quench events when local thresholds are reached
            in the BVP envelope using the integrated quench detection system.

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Quench detection results including:
                - quench_locations: Spatial locations of quenches
                - quench_types: Types of quenches detected
                - energy_dumped: Energy dumped at each quench
        """
        if self.quench_detector is not None:
            return self.quench_detector.detect_quenches(envelope)
        else:
            return {"quench_locations": [], "quench_types": [], "energy_dumped": []}

    def get_bvp_core(self) -> Optional[BVPCore]:
        """
        Get the integrated BVP core.

        Physical Meaning:
            Returns the BVP framework integration if available.

        Returns:
            Optional[BVPCore]: BVP core integration or None.
        """
        return self.bvp_core

    def set_bvp_core(self, bvp_core: BVPCore) -> None:
        """
        Set the BVP core integration.

        Physical Meaning:
            Updates the BVP framework integration and reinitializes
            the quench detection system.

        Args:
            bvp_core (BVPCore): BVP framework integration.
        """
        self.bvp_core = bvp_core
        if self.bvp_core is not None:
            quench_config = self.config.get("quench_detection", {})
            self.quench_detector = QuenchDetector(quench_config)

    def __repr__(self) -> str:
        """String representation of the integrator."""
        return (
            f"{self.__class__.__name__}(domain={self.domain}, "
            f"type={self.get_integrator_type()})"
        )
