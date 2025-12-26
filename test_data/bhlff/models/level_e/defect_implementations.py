"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Defect implementations for Level E experiments in 7D phase field theory.

This module implements specific defect types including vortex defects
and multi-defect systems.

Theoretical Background:
    Different types of topological defects have distinct properties
    and behaviors. Vortex defects are fundamental structures with
    quantized circulation, while multi-defect systems exhibit
    complex collective dynamics.

Mathematical Foundation:
    Vortex defects have quantized circulation: ∮v·dl = 2πn where
    n is the winding number. Multi-defect systems follow collective
    dynamics governed by interaction potentials.

Example:
    >>> vortex = VortexDefect(domain, physics_params)
    >>> field = vortex.create_vortex_profile(position)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from .defect_core import DefectModel
from .defect_dynamics import DefectDynamics
from .defect_interactions import DefectInteractions


class VortexDefect(DefectModel):
    """
    Vortex defect implementation.

    Physical Meaning:
        Represents a vortex defect with quantized circulation
        and localized phase winding in the field configuration.

    Mathematical Foundation:
        Vortex defects have quantized circulation: ∮v·dl = 2πn
        where n is the winding number and v is the velocity field.
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any]):
        """
        Initialize vortex defect.

        Physical Meaning:
            Sets up a vortex defect with specified physical parameters
            and computational domain.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
        """
        super().__init__(domain, physics_params)
        self._setup_vortex_parameters()

    def _setup_vortex_parameters(self) -> None:
        """
        Setup parameters specific to vortex defects.

        Physical Meaning:
            Initializes vortex-specific parameters including
            circulation, core size, and velocity field properties.
        """
        self.circulation = self.params.get("circulation", 1)
        self.core_radius = self.params.get("core_radius", 0.1)
        self.velocity_amplitude = self.params.get("velocity_amplitude", 1.0)

    def create_vortex_profile(self, position: np.ndarray) -> np.ndarray:
        """
        Create vortex field profile.

        Physical Meaning:
            Generates a field configuration with vortex structure
            at the specified position, including phase winding
            and amplitude profile.

        Mathematical Foundation:
            Creates field with phase φ = n·arctan2(y-y₀, x-x₀) and
            amplitude A(r) = tanh(r/ξ) where n is the winding number.

        Args:
            position: Position of vortex center

        Returns:
            Complex field configuration with vortex
        """
        # Create coordinate grids
        x = np.linspace(0, self.domain.L, self.domain.N, endpoint=False)
        y = np.linspace(0, self.domain.L, self.domain.N, endpoint=False)
        z = np.linspace(0, self.domain.L, self.domain.N, endpoint=False)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Compute distances from vortex center
        dx = X - position[0]
        dy = Y - position[1]
        dz = Z - position[2]
        r = np.sqrt(dx**2 + dy**2 + dz**2)

        # Create amplitude profile
        amplitude = self._create_vortex_amplitude(r)

        # Create phase profile with circulation
        phase = self.circulation * np.arctan2(dy, dx)

        # Combine amplitude and phase
        field = amplitude * np.exp(1j * phase)

        return field

    def _create_vortex_amplitude(self, r: np.ndarray) -> np.ndarray:
        """
        Create amplitude profile for vortex.

        Physical Meaning:
            Generates the amplitude profile that determines the
            spatial extent of the vortex, with zero amplitude
            at the core and smooth transition to the background.
        """
        coherence_length = self.params.get("coherence_length", 0.5)

        # Tanh profile for smooth amplitude transition
        amplitude = np.tanh(r / coherence_length)

        # Ensure zero amplitude at core
        amplitude = np.where(r < self.core_radius, 0.0, amplitude)

        return amplitude


class MultiDefectSystem(DefectModel):
    """
    Multi-defect system implementation.

    Physical Meaning:
        Represents a system of multiple topological defects
        with complex interactions and collective dynamics.

    Mathematical Foundation:
        Multi-defect systems follow collective dynamics governed
        by interaction potentials and topological constraints.
    """

    def __init__(
        self,
        domain: "Domain",
        physics_params: Dict[str, Any],
        initial_defects: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize multi-defect system.

        Physical Meaning:
            Sets up a system of multiple defects with specified
            initial positions and charges.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
            initial_defects: List of initial defect configurations
        """
        super().__init__(domain, physics_params)

        # Initialize defect dynamics and interactions
        self.dynamics = DefectDynamics(domain, physics_params)
        self.interactions = DefectInteractions(domain, physics_params)

        # Setup initial defects
        if initial_defects is None:
            self.defects = []
        else:
            self.defects = initial_defects.copy()

        self._setup_multi_defect_parameters()

    def _setup_multi_defect_parameters(self) -> None:
        """
        Setup parameters for multi-defect system.

        Physical Meaning:
            Initializes parameters specific to multi-defect
            systems including interaction ranges, annihilation
            criteria, and collective dynamics.
        """
        self.max_defects = self.params.get("max_defects", 10)
        self.annihilation_radius = self.params.get("annihilation_radius", 0.2)
        self.interaction_cutoff = self.params.get("interaction_cutoff", 2.0)
        self.equilibration_time = self.params.get("equilibration_time", 1.0)

    def _setup_interaction_potential(self) -> None:
        """
        Setup interaction potential for multi-defect system.

        Physical Meaning:
            Initializes the interaction potential between multiple
            defects, including Green functions and screening effects.
        """
        # Use the interactions module for setup
        self.interactions._setup_interaction_parameters()

    def compute_interaction_forces(self) -> np.ndarray:
        """
        Compute interaction forces between all defects.

        Physical Meaning:
            Calculates the forces acting on each defect due to
            interactions with all other defects in the system.

        Returns:
            Array of force vectors for each defect
        """
        if len(self.defects) < 2:
            return np.array([])

        # Extract positions and charges
        positions = [defect["position"] for defect in self.defects]
        charges = [defect["charge"] for defect in self.defects]

        # Compute forces using interactions module
        forces = self.interactions.compute_interaction_forces(positions, charges)

        return np.array(forces)

    def _compute_pair_force(
        self, defect_i: Dict[str, Any], defect_j: Dict[str, Any]
    ) -> np.ndarray:
        """
        Compute force between defect pair.

        Physical Meaning:
            Calculates the force between two specific defects
            based on their charges and separation.

        Args:
            defect_i: First defect configuration
            defect_j: Second defect configuration

        Returns:
            Force vector on defect i due to defect j
        """
        # Compute separation
        r_ij = defect_j["position"] - defect_i["position"]
        r_magnitude = np.linalg.norm(r_ij)

        # Compute force using interactions module
        force = self.interactions._compute_pair_force(
            r_ij, r_magnitude, defect_i["charge"], defect_j["charge"]
        )

        return force

    def simulate_defect_annihilation(self, defect_pair: List[int]) -> Dict[str, Any]:
        """
        Simulate annihilation of defect-antidefect pair.

        Physical Meaning:
            Models the annihilation process where a defect and
            antidefect approach and annihilate, releasing energy
            and creating topological transitions.

        Args:
            defect_pair: Indices of defect and antidefect

        Returns:
            Dictionary containing annihilation results
        """
        if len(defect_pair) != 2:
            return {"annihilated": False, "reason": "Invalid defect pair"}

        i, j = defect_pair

        # Extract defect information
        positions = [defect["position"] for defect in self.defects]
        charges = [defect["charge"] for defect in self.defects]

        # Use interactions module for annihilation simulation
        result = self.interactions.simulate_defect_annihilation(
            defect_pair, positions, charges
        )

        # If annihilation occurred, remove defects from system
        if result["annihilated"]:
            # Remove defects (in reverse order to maintain indices)
            self.defects.pop(max(i, j))
            self.defects.pop(min(i, j))

        return result

    def add_defect(self, position: np.ndarray, charge: int) -> None:
        """
        Add new defect to the system.

        Physical Meaning:
            Adds a new topological defect to the multi-defect
            system with specified position and charge.

        Args:
            position: Position of new defect
            charge: Charge of new defect
        """
        if len(self.defects) >= self.max_defects:
            raise ValueError(f"Maximum number of defects ({self.max_defects}) exceeded")

        new_defect = {
            "position": np.array(position),
            "charge": charge,
            "id": len(self.defects),
        }

        self.defects.append(new_defect)

    def remove_defect(self, defect_id: int) -> None:
        """
        Remove defect from the system.

        Physical Meaning:
            Removes a defect from the multi-defect system,
            typically after annihilation or other processes.

        Args:
            defect_id: ID of defect to remove
        """
        if 0 <= defect_id < len(self.defects):
            self.defects.pop(defect_id)

    def get_system_energy(self) -> float:
        """
        Compute total energy of the multi-defect system.

        Physical Meaning:
            Calculates the total energy of the system including
            individual defect energies and interaction energies.

        Returns:
            Total system energy
        """
        if len(self.defects) < 2:
            return 0.0

        # Extract positions and charges
        positions = [defect["position"] for defect in self.defects]
        charges = [defect["charge"] for defect in self.defects]

        # Compute interaction potential energy
        interaction_energy = self.interactions.compute_interaction_potential(
            positions, charges
        )

        return interaction_energy

    def evolve_system(self, time_step: float) -> None:
        """
        Evolve the multi-defect system in time.

        Physical Meaning:
            Advances the system in time, updating defect positions
            and handling interactions and annihilation processes.

        Args:
            time_step: Time step for evolution
        """
        if len(self.defects) < 2:
            return

        # Compute forces
        forces = self.compute_interaction_forces()

        # Update positions
        for i, defect in enumerate(self.defects):
            if i < len(forces):
                # Simple Euler integration
                defect["position"] += time_step * forces[i]

        # Check for annihilation
        self._check_and_handle_annihilation()

    def _check_and_handle_annihilation(self) -> None:
        """
        Check for and handle defect annihilation.

        Physical Meaning:
            Checks if any defect pairs are close enough for
            annihilation and handles the annihilation process.
        """
        n_defects = len(self.defects)

        # Check all pairs for annihilation
        for i in range(n_defects):
            for j in range(i + 1, n_defects):
                # Check if defects have opposite charges
                if self.defects[i]["charge"] * self.defects[j]["charge"] < 0:
                    # Check separation
                    r_ij = self.defects[j]["position"] - self.defects[i]["position"]
                    r_magnitude = np.linalg.norm(r_ij)

                    if r_magnitude < self.annihilation_radius:
                        # Handle annihilation
                        self.simulate_defect_annihilation([i, j])
                        # Break to avoid index issues
                        return
