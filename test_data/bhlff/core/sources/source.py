"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Abstract source base class.

This module provides the abstract base class for all source terms in the
7D phase field theory.

Physical Meaning:
    Sources represent external excitations or initial conditions that drive
    the evolution of phase field configurations in the 7D theory.

Mathematical Foundation:
    Sources appear as s(x) in phase field equations:
    L_β a = s(x)
    where L_β is the fractional Riesz operator and s(x) is the source term.

Example:
    >>> source = BVPSource(domain, config)
    >>> source_field = source.generate()
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any

from ..domain import Domain


class Source(ABC):
    """
    Abstract base class for source terms.

    Physical Meaning:
        Provides the fundamental interface for all source terms in the
        7D phase field theory, representing external excitations or
        initial conditions that drive phase field evolution.

    Mathematical Foundation:
        Sources appear as s(x) in phase field equations:
        L_β a = s(x)
        where L_β is the fractional Riesz operator.

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): Source configuration.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize source.

        Physical Meaning:
            Sets up the source with computational domain and configuration
            parameters for generating source terms.

        Args:
            domain (Domain): Computational domain for the source.
            config (Dict[str, Any]): Source configuration parameters.
        """
        self.domain = domain
        self.config = config

    @abstractmethod
    def generate(self) -> np.ndarray:
        """
        Generate source field.

        Physical Meaning:
            Generates the source field s(x) that represents external
            excitations or initial conditions for phase field evolution.

        Mathematical Foundation:
            Creates the source term s(x) for the phase field equation
            L_β a = s(x).

        Returns:
            np.ndarray: Source field s(x).

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement generate method")

    @abstractmethod
    def get_source_type(self) -> str:
        """
        Get the source type.

        Physical Meaning:
            Returns the type of source being used.

        Returns:
            str: Source type.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement get_source_type method")

    def get_domain(self) -> Domain:
        """
        Get the computational domain.

        Physical Meaning:
            Returns the computational domain for the source.

        Returns:
            Domain: Computational domain.
        """
        return self.domain

    def get_config(self) -> Dict[str, Any]:
        """
        Get the source configuration.

        Physical Meaning:
            Returns the configuration parameters for the source.

        Returns:
            Dict[str, Any]: Source configuration.
        """
        return self.config.copy()

    def __repr__(self) -> str:
        """String representation of the source."""
        return (
            f"{self.__class__.__name__}(domain={self.domain}, "
            f"type={self.get_source_type()})"
        )
