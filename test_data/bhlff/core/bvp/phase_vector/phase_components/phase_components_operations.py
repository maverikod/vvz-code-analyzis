"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase components operations.
"""

import numpy as np
from typing import List, Optional


class PhaseComponentsOperations:
    """
    Phase components operations.

    Physical Meaning:
        Provides methods to get components, compute total phase,
        and update components from envelope.
    """

    def __init__(self, domain, theta_components: List[np.ndarray]):
        """
        Initialize operations manager.

        Args:
            domain: Computational domain.
            theta_components (List[np.ndarray]): Phase components.
        """
        self.domain = domain
        self.theta_components = theta_components

    def get_components(self) -> List[np.ndarray]:
        """
        Get the three U(1) phase components Θ_a (a=1..3).

        Physical Meaning:
            Returns the three independent U(1) phase components
            that form the U(1)³ structure.
            Returns BlockedField objects for large domains, which
            can be accessed transparently like numpy arrays.

        Returns:
            List[np.ndarray]: List of three phase components Θ_a.
                May be BlockedField objects for large domains, which
                support numpy-like indexing and operations.
        """
        # Return components (may be BlockedField for large domains)
        # BlockedField supports numpy-like operations transparently
        return list(self.theta_components)

    def get_total_phase(self, coupling_matrix: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Get the total phase from U(1)³ structure.

        Physical Meaning:
            Computes the total phase by combining the three
            U(1) components with proper coupling.

        Mathematical Foundation:
            Θ_total = Σ_a Θ_a + Σ_{a,b} g_{ab} Θ_a Θ_b
            where g_{ab} are the coupling coefficients.

        Args:
            coupling_matrix (np.ndarray, optional): Coupling matrix for components.

        Returns:
            np.ndarray: Total phase field.
        """
        # Handle BlockedField for large domains
        first_component = self.theta_components[0]
        
        # Check if we're using BlockedField
        from bhlff.core.sources.blocked_field_generator import BlockedField
        
        if isinstance(first_component, BlockedField):
            # Use block-based computation for total phase
            return self._compute_total_phase_blocked(coupling_matrix)
        else:
            # Direct computation for small domains
            total_phase = np.zeros_like(first_component)
            for theta_a in self.theta_components:
                total_phase += theta_a

            # Add coupling terms if provided
            if coupling_matrix is not None:
                for i, theta_i in enumerate(self.theta_components):
                    for j, theta_j in enumerate(self.theta_components):
                        if i != j:
                            coupling_strength = coupling_matrix[i, j]
                            total_phase += coupling_strength * theta_i * theta_j

            return total_phase

    def _compute_total_phase_blocked(self, coupling_matrix: Optional[np.ndarray] = None):
        """
        Compute total phase using block processing for large domains.
        
        Physical Meaning:
            Computes total phase by processing blocks individually,
            enabling memory-efficient computation for large 7D domains.
        """
        from bhlff.core.sources.blocked_field_generator import BlockedFieldGenerator, BlockedField
        
        # Create generator function for total phase
        def total_phase_generator(domain, slice_config, config):
            """Generate total phase block."""
            block_shape = slice_config["shape"]
            total_block = np.zeros(block_shape, dtype=complex)
            
            # Sum all component blocks
            # Get block indices from slice_config
            block_start = slice_config.get("start", (0,) * len(block_shape))
            block_end = slice_config.get("end", block_shape)
            
            for theta_component in self.theta_components:
                if isinstance(theta_component, BlockedField):
                    # Get block from BlockedField using slicing
                    # BlockedField supports __getitem__ with slices
                    slices = tuple(slice(block_start[d], block_end[d]) 
                                  for d in range(len(block_shape)))
                    component_block = theta_component[slices]
                else:
                    # Direct array access
                    slices = tuple(slice(block_start[d], block_end[d]) 
                                  for d in range(len(block_shape)))
                    component_block = theta_component[slices]
                
                total_block += component_block
            
            # Add coupling terms if provided
            if coupling_matrix is not None:
                for i in range(len(self.theta_components)):
                    for j in range(len(self.theta_components)):
                        if i != j:
                            if isinstance(self.theta_components[i], BlockedField):
                                slices = tuple(slice(block_start[d], block_end[d]) 
                                              for d in range(len(block_shape)))
                                block_i = self.theta_components[i][slices]
                            else:
                                slices = tuple(slice(block_start[d], block_end[d]) 
                                              for d in range(len(block_shape)))
                                block_i = self.theta_components[i][slices]
                            
                            if isinstance(self.theta_components[j], BlockedField):
                                slices = tuple(slice(block_start[d], block_end[d]) 
                                              for d in range(len(block_shape)))
                                block_j = self.theta_components[j][slices]
                            else:
                                slices = tuple(slice(block_start[d], block_end[d]) 
                                              for d in range(len(block_shape)))
                                block_j = self.theta_components[j][slices]
                            
                            coupling_strength = coupling_matrix[i, j]
                            total_block += coupling_strength * block_i * block_j
            
            return total_block
        
        # Create BlockedFieldGenerator for total phase
        generator = BlockedFieldGenerator(self.domain, total_phase_generator)
        return generator.get_field()

    def update_components(self, envelope: np.ndarray) -> None:
        """
        Update phase components from solved envelope.

        Physical Meaning:
            Updates the three U(1) phase components Θ_a (a=1..3)
            from the solved BVP envelope field.

        Mathematical Foundation:
            Extracts phase components from the envelope solution
            and updates the U(1)³ phase structure.

        Args:
            envelope (np.ndarray): Solved BVP envelope in 7D space-time.
        """
        # If envelope is a vector field, extract components
        if envelope.ndim > self.domain.dimensions:
            # Envelope has additional dimensions for phase components
            for a in range(3):
                if a < envelope.shape[-1]:  # Check if component exists
                    self.theta_components[a] = envelope[..., a]
        else:
            # Single envelope field - distribute to components
            for a in range(3):
                # Each component gets a phase-shifted version
                phase_shift = 2 * np.pi * a / 3
                self.theta_components[a] = envelope * np.exp(1j * phase_shift)

