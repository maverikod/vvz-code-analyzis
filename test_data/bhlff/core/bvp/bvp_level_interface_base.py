"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base BVP level interface implementation.

This module defines the abstract base class for all BVP level interfaces,
providing the common interface and structure for integrating BVP with
all levels A-G of the 7D phase field theory.

Physical Meaning:
    BVP serves as the central framework where all observed "modes"
    are envelope modulations and beatings of the Base High-Frequency Field.
    This module provides the base interface for levels A-G to interact with BVP.

Mathematical Foundation:
    Each level provides specific mathematical operations that work
    with BVP envelope data, transforming it according to level-specific
    requirements while maintaining BVP framework compliance.

Example:
    >>> class MyLevelInterface(BVPLevelInterface):
    ...     def process_bvp_data(self, envelope, **kwargs):
    ...         # Implementation
    ...         return results
"""

import numpy as np
from typing import Dict, Any
from abc import ABC, abstractmethod


class BVPLevelInterface(ABC):
    """
    Abstract base class for BVP level interfaces.

    Physical Meaning:
        Defines the interface for integrating BVP with specific levels
        of the 7D phase field theory.
    """

    @abstractmethod
    def process_bvp_data(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Process BVP envelope data for this level.

        Physical Meaning:
            Transforms BVP envelope data according to level-specific
            requirements while maintaining BVP framework compliance.

        Args:
            envelope (np.ndarray): BVP envelope in 7D space-time.
            **kwargs: Level-specific parameters.

        Returns:
            Dict[str, Any]: Processed data for this level.
        """
        raise NotImplementedError("Subclasses must implement process_bvp_data method")
