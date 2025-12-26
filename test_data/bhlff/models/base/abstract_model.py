"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Abstract base class for BHLFF models.

This module contains the AbstractModel base class for all model components
in the BHLFF framework, providing common interfaces and functionality.

Physical Meaning:
    AbstractModel defines the fundamental interface for all model components
    in the 7D phase field theory implementation, ensuring consistent behavior
    and interoperability.

Mathematical Foundation:
    Base class implements common mathematical operations and interfaces
    required for analyzing different aspects of the phase field theory.

Example:
    >>> from bhlff.models.base import AbstractModel
    >>> class MyModel(AbstractModel):
    ...     def analyze(self, data):
    ...         pass
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ...core.domain import Domain


class AbstractModel(ABC):
    """
    Abstract base class for all BHLFF models.

    Physical Meaning:
        Provides the fundamental interface for all model components
        in the 7D phase field theory, ensuring consistent behavior
        and interoperability across different model types.

    Mathematical Foundation:
        Defines common mathematical operations and interfaces
        required for analyzing different aspects of the phase field theory.

    Attributes:
        domain (Domain): Computational domain for simulations
    """

    def __init__(self, domain: "Domain"):
        """
        Initialize abstract model.

        Physical Meaning:
            Sets up the base functionality for all model components,
            providing access to domain information.

        Args:
            domain (Domain): Computational domain
        """
        self.domain = domain
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def analyze(self, data: Any) -> Dict[str, Any]:
        """
        Analyze data for this model.

        Physical Meaning:
            Performs model-specific analysis of the input data,
            extracting relevant physical quantities and properties.

        Mathematical Foundation:
            Implements model-specific mathematical operations
            for analyzing the data structure and dynamics.

        Args:
            data (Any): Input data to analyze

        Returns:
            Dict: Analysis results
        """
        pass

    def validate_domain(self) -> bool:
        """
        Validate computational domain.

        Physical Meaning:
            Checks that the computational domain is properly
            configured for the model to function correctly.

        Returns:
            bool: True if domain is valid
        """
        # Basic validation - can be overridden by subclasses
        return self.domain is not None

    def get_domain_info(self) -> Dict[str, Any]:
        """
        Get domain information.

        Physical Meaning:
            Retrieves information about the computational domain,
            including dimensions, size, and resolution.

        Returns:
            Dict: Domain information
        """
        return {
            "shape": self.domain.shape,
            "L": getattr(self.domain, "L", None),
            "N": getattr(self.domain, "N", None),
            "dimensions": getattr(self.domain, "dimensions", None),
        }

    def log_analysis_start(self, analysis_type: str) -> None:
        """
        Log analysis start.

        Physical Meaning:
            Provides consistent logging for analysis operations,
            helping with debugging and monitoring.

        Args:
            analysis_type (str): Type of analysis being performed
        """
        self.logger.info(f"Starting {analysis_type} analysis")

    def log_analysis_complete(
        self, analysis_type: str, results: Dict[str, Any]
    ) -> None:
        """
        Log analysis completion.

        Physical Meaning:
            Provides consistent logging for analysis completion,
            including summary of results.

        Args:
            analysis_type (str): Type of analysis performed
            results (Dict): Analysis results
        """
        self.logger.info(f"{analysis_type} analysis completed")
        self.logger.debug(f"Results: {list(results.keys())}")

    def __str__(self) -> str:
        """String representation of the model."""
        return f"{self.__class__.__name__}(domain={self.domain})"

    def __repr__(self) -> str:
        """Detailed string representation of the model."""
        return f"{self.__class__.__name__}(domain={self.domain})"
