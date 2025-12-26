"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base model class for BHLFF models.

This module contains the ModelBase class for all model components
in the BHLFF framework, providing common interfaces and functionality.

Physical Meaning:
    ModelBase defines the fundamental interface for all model components
    in the 7D phase field theory implementation, ensuring consistent behavior
    and interoperability.

Mathematical Foundation:
    Base class implements common mathematical operations and interfaces
    required for analyzing different aspects of the phase field theory.

Example:
    >>> from bhlff.models.base import ModelBase
    >>> class MyModel(ModelBase):
    ...     def analyze(self, data):
    ...         pass
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging
import numpy as np

if TYPE_CHECKING:
    from ...core.domain import Domain


class ModelBase(ABC):
    """
    Base class for all BHLFF models.

    Physical Meaning:
        Provides the fundamental interface for all model components
        in the 7D phase field theory, ensuring consistent behavior
        and interoperability across different model types.

    Mathematical Foundation:
        Defines common mathematical operations and interfaces
        required for analyzing different aspects of the phase field theory.

    Attributes:
        domain (Optional[Domain]): Computational domain for simulations
        logger (logging.Logger): Logger for the model
    """

    def __init__(self, domain: Optional["Domain"] = None):
        """
        Initialize base model.

        Physical Meaning:
            Sets up the base functionality for all model components,
            providing access to domain information and logging.

        Args:
            domain (Optional[Domain]): Computational domain
        """
        self.domain = domain
        self.logger = logging.getLogger(self.__class__.__name__)

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
        if self.domain is None:
            return {}

        return {
            "shape": getattr(self.domain, "shape", None),
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

    def validate_array(self, array: np.ndarray, name: str = "array") -> bool:
        """
        Validate numpy array.

        Physical Meaning:
            Checks that the array is properly formatted and contains
            valid numerical data for the model calculations.

        Args:
            array (np.ndarray): Array to validate
            name (str): Name of the array for error messages

        Returns:
            bool: True if array is valid
        """
        if not isinstance(array, np.ndarray):
            self.logger.error(f"{name} is not a numpy array")
            return False

        if not np.isfinite(array).all():
            self.logger.error(f"{name} contains non-finite values")
            return False

        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """
        Validate model parameters.

        Physical Meaning:
            Checks that the model parameters are within
            physically reasonable ranges and are consistent.

        Args:
            parameters (Dict[str, Any]): Parameters to validate

        Returns:
            bool: True if parameters are valid
        """
        # Basic validation - can be overridden by subclasses
        for key, value in parameters.items():
            if isinstance(value, (int, float)):
                if not np.isfinite(value):
                    self.logger.error(f"Parameter {key} is not finite")
                    return False

        return True

    def compute_statistics(self, data: np.ndarray) -> Dict[str, float]:
        """
        Compute basic statistics for data.

        Physical Meaning:
            Computes fundamental statistical properties of the data,
            providing insight into the distribution and characteristics.

        Args:
            data (np.ndarray): Data to analyze

        Returns:
            Dict[str, float]: Statistical properties
        """
        if not self.validate_array(data, "data"):
            return {}

        return {
            "mean": float(np.mean(data)),
            "std": float(np.std(data)),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "rms": float(np.sqrt(np.mean(data**2))),
            "variance": float(np.var(data)),
        }

    def __str__(self) -> str:
        """String representation of the model."""
        return f"{self.__class__.__name__}(domain={self.domain})"

    def __repr__(self) -> str:
        """Detailed string representation of the model."""
        return f"{self.__class__.__name__}(domain={self.domain})"
