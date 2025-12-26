"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Specific soliton implementations for Level E experiments in 7D phase field theory.

This module contains concrete implementations of different types of solitons:
- BaryonSoliton: B=1 topological charge (proton/neutron)
- SkyrmionSoliton: Arbitrary topological charge

Theoretical Background:
    Implements specific soliton types with their characteristic properties
    and constraints, including Finkelstein-Rubinstein constraints for
    fermionic statistics.

Example:
    >>> baryon = BaryonSoliton(domain, physics_params)
    >>> solution = baryon.find_soliton_solution(initial_guess)
"""

import numpy as np
from typing import Dict, Any
from .soliton_core import SolitonModel


class BaryonSoliton(SolitonModel):
    """
    Baryon soliton with B=1 topological charge.

    Physical Meaning:
        Represents proton/neutron as topological soliton with unit
        baryon number in 7D phase field theory. The soliton is realized
        as a phase pattern on the U(1)^3 substrate with controlled
        winding over φ-coordinates, subject to Finkelstein-Rubinstein
        constraints that ensure fermionic statistics.

    Mathematical Foundation:
        Implements B=1 soliton with U(1)^3 phase winding Θ(x,φ) ∈ T^3_φ
        and FR constraints ensuring that rotation by 2π changes the sign
        of the wave function, providing fermionic statistics. The classical
        SU(2) hedgehog pattern is a 4D pedagogical limit, not the core
        7D construction.
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any]):
        """
        Initialize baryon soliton.

        Physical Meaning:
            Sets up a soliton with unit baryon number and FR constraints
            to represent a proton or neutron.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
        """
        super().__init__(domain, physics_params)
        self.baryon_number = 1
        self._setup_fr_constraints()

    def _setup_fr_constraints(self) -> None:
        """
        Setup Finkelstein-Rubinstein constraints for fermionic statistics.

        Physical Meaning:
            Implements the Finkelstein-Rubinstein constraints that ensure
            the soliton has fermionic statistics by requiring that a
            2π rotation changes the sign of the wave function.

        Mathematical Foundation:
            Under 2π rotation: ψ → -ψ, ensuring fermionic statistics
            for the soliton.
        """
        self.fr_rotation_angle = 2 * np.pi
        self.fr_sign_change = True
        self.fr_constraint_strength = self.params.get("fr_constraint_strength", 1.0)

        # Setup FR constraint parameters
        self.fr_rotation_axis = self.params.get("fr_rotation_axis", [0, 0, 1])
        self.fr_rotation_center = self.params.get("fr_rotation_center", [0, 0, 0])

        # Normalize rotation axis
        self.fr_rotation_axis = np.array(self.fr_rotation_axis)
        self.fr_rotation_axis = self.fr_rotation_axis / np.linalg.norm(
            self.fr_rotation_axis
        )

    def apply_fr_constraints(self, field: np.ndarray) -> np.ndarray:
        """
        Apply Finkelstein-Rubinstein constraints to field.

        Physical Meaning:
            Applies the FR constraints to ensure fermionic statistics
            by enforcing the sign change under 2π rotation.

        Args:
            field: Field configuration

        Returns:
            Field with FR constraints applied
        """
        # Apply 2π rotation
        rotated_field = self._apply_rotation(field, self.fr_rotation_angle)

        # Apply sign change for fermionic statistics
        if self.fr_sign_change:
            rotated_field = -rotated_field

        # Apply constraint strength
        constrained_field = (
            1 - self.fr_constraint_strength
        ) * field + self.fr_constraint_strength * rotated_field

        return constrained_field

    def _apply_rotation(self, field: np.ndarray, angle: float) -> np.ndarray:
        """
        Apply rotation to field configuration.

        Physical Meaning:
            Rotates the field configuration by the specified angle
            around the rotation axis.

        Args:
            field: Field configuration
            angle: Rotation angle in radians

        Returns:
            Rotated field configuration
        """
        # Create rotation matrix
        axis = self.fr_rotation_axis
        cos_angle = np.cos(angle)
        sin_angle = np.sin(angle)

        # Rodrigues' rotation formula
        K = np.array(
            [[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]]
        )

        R = np.eye(3) + sin_angle * K + (1 - cos_angle) * np.dot(K, K)

        # Apply rotation to field
        rotated_field = np.zeros_like(field)
        for i in range(field.shape[0]):
            for j in range(field.shape[1]):
                for k in range(field.shape[2]):
                    # Get position vector
                    pos = np.array([i, j, k]) - np.array(self.fr_rotation_center)

                    # Apply rotation
                    rotated_pos = np.dot(R, pos) + np.array(self.fr_rotation_center)

                    # Interpolate field value at rotated position
                    if (
                        0 <= rotated_pos[0] < field.shape[0]
                        and 0 <= rotated_pos[1] < field.shape[1]
                        and 0 <= rotated_pos[2] < field.shape[2]
                    ):
                        rotated_field[i, j, k] = self._interpolate_field(
                            field, rotated_pos
                        )

        return rotated_field

    def _interpolate_field(self, field: np.ndarray, position: np.ndarray) -> np.ndarray:
        """
        Interpolate field value at given position.

        Physical Meaning:
            Computes the field value at a non-integer position using
            trilinear interpolation.

        Args:
            field: Field configuration
            position: Position vector

        Returns:
            Interpolated field value
        """
        # Trilinear interpolation
        x, y, z = position

        # Get integer and fractional parts
        x0, y0, z0 = int(x), int(y), int(z)
        dx, dy, dz = x - x0, y - y0, z - z0

        # Ensure indices are within bounds
        x0 = max(0, min(x0, field.shape[0] - 1))
        y0 = max(0, min(y0, field.shape[1] - 1))
        z0 = max(0, min(z0, field.shape[2] - 1))

        x1 = min(x0 + 1, field.shape[0] - 1)
        y1 = min(y0 + 1, field.shape[1] - 1)
        z1 = min(z0 + 1, field.shape[2] - 1)

        # Interpolate
        c000 = field[x0, y0, z0]
        c001 = field[x0, y0, z1]
        c010 = field[x0, y1, z0]
        c011 = field[x0, y1, z1]
        c100 = field[x1, y0, z0]
        c101 = field[x1, y0, z1]
        c110 = field[x1, y1, z0]
        c111 = field[x1, y1, z1]

        # Trilinear interpolation formula
        c00 = c000 * (1 - dx) + c100 * dx
        c01 = c001 * (1 - dx) + c101 * dx
        c10 = c010 * (1 - dx) + c110 * dx
        c11 = c011 * (1 - dx) + c111 * dx

        c0 = c00 * (1 - dy) + c10 * dy
        c1 = c01 * (1 - dy) + c11 * dy

        return c0 * (1 - dz) + c1 * dz


class SkyrmionSoliton(SolitonModel):
    """
    Skyrmion soliton with arbitrary topological charge.

    Physical Meaning:
        General topological soliton with arbitrary winding number in 7D
        phase field theory, representing extended baryonic matter or
        exotic states. The soliton is realized as a phase pattern on
        the U(1)^3 substrate with controlled winding over φ-coordinates.

    Mathematical Foundation:
        Implements soliton with arbitrary topological charge B using
        U(1)^3 phase winding Θ(x,φ) ∈ T^3_φ, allowing for multi-baryon
        states and exotic configurations. The classical SU(2) hedgehog
        pattern is a 4D pedagogical limit, not the core 7D construction.
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any], charge: int):
        """
        Initialize skyrmion soliton.

        Physical Meaning:
            Sets up a soliton with specified topological charge,
            representing multi-baryon states or exotic configurations.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
            charge: Topological charge (baryon number)
        """
        super().__init__(domain, physics_params)
        self.charge = charge
        self._setup_charge_specific_terms()

    def _setup_charge_specific_terms(self) -> None:
        """
        Setup terms specific to topological charge.

        Physical Meaning:
            Initializes charge-specific terms and constraints that
            depend on the topological charge of the soliton.

        Mathematical Foundation:
            Different topological charges require different
            boundary conditions and constraint terms.
        """
        if self.charge == 1:
            self._setup_baryon_terms()
        elif self.charge > 1:
            self._setup_multi_baryon_terms()
        else:
            self._setup_antibaryon_terms()

    def _setup_baryon_terms(self) -> None:
        """Setup terms for B=1 soliton."""
        self.boundary_condition = "u1_phase_winding"
        self.constraint_type = "single_baryon"
        self.charge_specific_coupling = self.params.get("baryon_coupling", 1.0)

    def _setup_multi_baryon_terms(self) -> None:
        """Setup terms for B>1 soliton."""
        self.boundary_condition = "multi_u1_phase_winding"
        self.constraint_type = "multi_baryon"
        self.charge_specific_coupling = self.params.get("multi_baryon_coupling", 1.0)

        # Setup multi-baryon specific parameters
        self.baryon_separation = self.params.get("baryon_separation", 1.0)
        self.interaction_strength = self.params.get("interaction_strength", 0.1)

    def _setup_antibaryon_terms(self) -> None:
        """Setup terms for B<0 soliton."""
        self.boundary_condition = "anti_u1_phase_winding"
        self.constraint_type = "antibaryon"
        self.charge_specific_coupling = self.params.get("antibaryon_coupling", 1.0)

        # Setup antibaryon specific parameters
        self.antibaryon_coupling = self.params.get("antibaryon_coupling", -1.0)
