"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base BVP Postulate class implementation.

This module defines the abstract base class for all BVP postulates,
providing the common interface and structure.

Theoretical Background:
    BVP postulates are operational models that validate specific
    properties of the BVP field. Each postulate implements a
    specific mathematical operation to verify field characteristics.

Example:
    >>> class MyPostulate(BVPPostulate):
    ...     def apply(self, envelope, **kwargs):
    ...         # Implementation
    ...         return results
"""

import numpy as np
from typing import Dict, Any
from abc import ABC, abstractmethod


class BVPPostulate(ABC):
    """
    Abstract base class for BVP postulates.

    Physical Meaning:
        Defines the interface for implementing BVP postulates as
        operational models with specific mathematical operations.

    Mathematical Foundation:
        Each postulate implements a specific mathematical operation
        to validate BVP field properties and ensure physical consistency.
    """

    @abstractmethod
    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply the postulate to the envelope.

        Physical Meaning:
            Performs the mathematical operation specific to this
            postulate to validate BVP field properties.

        Mathematical Foundation:
            Each postulate implements a specific mathematical
            operation to verify field characteristics.

        Args:
            envelope (np.ndarray): BVP envelope in 7D space-time.
                Represents the field configuration to be validated.
            **kwargs: Additional parameters specific to the postulate.
                May include thresholds, analysis parameters, etc.

        Returns:
            Dict[str, Any]: Results of applying the postulate.
                Must include 'postulate_satisfied' key indicating
                whether the postulate is satisfied.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement apply method")
