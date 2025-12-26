"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base BVP integration interface for all levels A-G.

This module provides the base interface for BVP integration with all levels
of the 7D phase field theory, ensuring consistent data flow and proper
coordination between different system components.

Physical Meaning:
    Provides the fundamental interface for integrating BVP framework with
    all levels of the 7D theory, ensuring that BVP serves as the central
    backbone for all system operations.

Mathematical Foundation:
    Implements base integration protocols that maintain physical consistency
    and mathematical rigor across all levels while providing appropriate
    data transformations for each level's specific requirements.

Example:
    >>> integrator = BVPLevelIntegrator(bvp_core)
    >>> level_a_results = integrator.integrate_level_a(envelope)
    >>> level_b_results = integrator.integrate_level_b(envelope)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging
from abc import ABC, abstractmethod

from bhlff.core.bvp import BVPCore


class BVPLevelIntegrationBase(ABC):
    """
    Abstract base class for BVP level integration.

    Physical Meaning:
        Defines the interface for integrating BVP framework with specific
        levels of the 7D phase field theory, ensuring consistent behavior
        across all integration implementations.

    Mathematical Foundation:
        Provides the base structure for integration protocols that maintain
        physical consistency and mathematical rigor across all levels.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize BVP level integration base.

        Physical Meaning:
            Sets up the integration interface with the BVP core framework,
            establishing the connection between BVP and level-specific operations.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def integrate_level(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Integrate BVP envelope with specific level.

        Physical Meaning:
            Transforms BVP envelope data according to level-specific
            requirements while maintaining BVP framework compliance.

        Args:
            envelope (np.ndarray): BVP envelope in 7D space-time.
            **kwargs: Level-specific parameters.

        Returns:
            Dict[str, Any]: Integration results for this level.
        """
        raise NotImplementedError("Subclasses must implement integrate_level method")

    def validate_envelope(self, envelope: np.ndarray) -> bool:
        """
        Validate BVP envelope data.

        Physical Meaning:
            Ensures that the BVP envelope data is physically meaningful
            and mathematically consistent before processing.

        Args:
            envelope (np.ndarray): BVP envelope to validate.

        Returns:
            bool: True if envelope is valid, False otherwise.
        """
        if envelope is None:
            self.logger.error("Envelope is None")
            return False

        if not isinstance(envelope, np.ndarray):
            self.logger.error("Envelope must be numpy array")
            return False

        if envelope.size == 0:
            self.logger.error("Envelope is empty")
            return False

        if not np.isfinite(envelope).all():
            self.logger.error("Envelope contains non-finite values")
            return False

        return True

    def get_bvp_constants(self) -> Dict[str, Any]:
        """
        Get BVP constants and configuration.

        Physical Meaning:
            Retrieves the BVP constants and configuration parameters
            needed for level-specific operations.

        Returns:
            Dict[str, Any]: BVP constants and configuration.
        """
        return self.bvp_core.constants.to_dict()

    def __repr__(self) -> str:
        """String representation of integration base."""
        return f"{self.__class__.__name__}(bvp_core={self.bvp_core})"
