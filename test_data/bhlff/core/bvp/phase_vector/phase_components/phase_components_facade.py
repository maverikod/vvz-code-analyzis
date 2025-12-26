"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for phase components management.
"""

from typing import Dict, Any, List, Optional

import numpy as np

from .phase_components_base import PhaseComponentsBase
from .phase_components_setup import PhaseComponentsSetup
from .phase_components_operations import PhaseComponentsOperations
from .phase_components_coherence import PhaseComponentsCoherence


class PhaseComponents(PhaseComponentsBase):
    """
    Management of three U(1) phase components Θ_a (a=1..3).

    Physical Meaning:
        Handles the three independent U(1) phase components that
        form the U(1)³ structure of the BVP field.

    Mathematical Foundation:
        Manages Θ₁, Θ₂, Θ₃ as independent U(1) phase degrees
        of freedom with weak hierarchical coupling.

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): Phase components configuration.
        theta_components (List[np.ndarray]): Three phase components Θ_a.
    """

    def __init__(self, domain, config: Dict[str, Any]) -> None:
        """Initialize phase components manager."""
        super().__init__(domain, config)
        self._operations = None
        self._coherence = None

    def _ensure_components_initialized(self) -> None:
        """
        Ensure phase components are initialized (lazy initialization).
        
        Physical Meaning:
            Initializes phase components on-demand if they haven't been
            initialized yet, enabling memory-efficient handling of large domains.
        """
        if not self._components_initialized:
            setup = PhaseComponentsSetup(self.domain, self.config)
            setup.setup_phase_components()
            self.theta_components = setup.theta_components
            self._components_initialized = True
            self._operations = PhaseComponentsOperations(self.domain, self.theta_components)
            self._coherence = PhaseComponentsCoherence(self.theta_components, self.use_cuda)

    def get_components(self) -> List[np.ndarray]:
        """
        Get the three U(1) phase components Θ_a (a=1..3).

        Physical Meaning:
            Returns the three independent U(1) phase components
            that form the U(1)³ structure.

        Returns:
            List[np.ndarray]: List of three phase components Θ_a.
        """
        self._ensure_components_initialized()
        return self._operations.get_components()

    def get_total_phase(self, coupling_matrix: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Get the total phase from U(1)³ structure.

        Physical Meaning:
            Computes the total phase by combining the three
            U(1) components with proper coupling.

        Args:
            coupling_matrix (np.ndarray, optional): Coupling matrix for components.

        Returns:
            np.ndarray: Total phase field.
        """
        self._ensure_components_initialized()
        return self._operations.get_total_phase(coupling_matrix)

    def update_components(self, envelope: np.ndarray) -> None:
        """
        Update phase components from solved envelope.

        Physical Meaning:
            Updates the three U(1) phase components Θ_a (a=1..3)
            from the solved BVP envelope field.

        Args:
            envelope (np.ndarray): Solved BVP envelope in 7D space-time.
        """
        self._ensure_components_initialized()
        self._operations.update_components(envelope)

    def compute_phase_coherence(self) -> np.ndarray:
        """
        Compute phase coherence measure.

        Physical Meaning:
            Computes a measure of phase coherence across the
            U(1)³ structure, indicating the degree of
            synchronization between the three phase components.

        Returns:
            np.ndarray: Phase coherence measure.
        """
        self._ensure_components_initialized()
        return self._coherence.compute_phase_coherence()

    def __repr__(self) -> str:
        """String representation of phase components."""
        cuda_status = "CUDA" if self.use_cuda else "CPU"
        return f"PhaseComponents(domain={self.domain}, num_components={len(self.theta_components)}, compute={cuda_status})"

