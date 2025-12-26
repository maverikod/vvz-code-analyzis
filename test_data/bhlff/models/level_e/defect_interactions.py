"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Defect interactions implementation for Level E experiments in 7D phase field theory.

This module implements interactions between topological defects including
forces, annihilation, and multi-defect systems.

Theoretical Background:
    Defect interactions are governed by Green functions and depend on
    the topological charges and separations between defects. Defects
    can attract, repel, or annihilate depending on their charges.

Mathematical Foundation:
    Interaction potential: U_int = Σᵢⱼ qᵢqⱼ G(rᵢⱼ) where G is the Green
    function and rᵢⱼ is the separation between defects i and j.

Example:
    >>> system = MultiDefectSystem(domain, physics_params)
    >>> forces = system.compute_interaction_forces()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from .defect_interactions_green import DefectInteractionsGreen
from .defect_interactions_energy import DefectInteractionsEnergy
from .defect_interactions_forces import DefectInteractionsForces


class DefectInteractions:
    """
    Defect interactions calculator for topological defects.

    Physical Meaning:
        Implements interactions between topological defects including
        forces, potentials, and annihilation processes.

    Mathematical Foundation:
        Computes interaction forces based on Green functions and
        topological charges: Fᵢ = -∇ᵢ Σⱼ qᵢqⱼ G(rᵢⱼ).
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any]):
        """
        Initialize defect interactions calculator.

        Physical Meaning:
            Sets up the computational framework for defect interactions
            including Green functions, interaction potentials, and
            annihilation processes.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
        """
        self.domain = domain
        self.params = physics_params
        self._setup_interaction_parameters()
        
        # Initialize helper classes
        self.green_computation = DefectInteractionsGreen(self.params)
        self.energy_computation = DefectInteractionsEnergy(
            self.params, self.green_computation
        )
        self.forces_computation = DefectInteractionsForces(
            self.params, self.green_computation
        )

    def _setup_interaction_parameters(self) -> None:
        """
        Setup parameters for defect interactions.

        Physical Meaning:
            Initializes the physical parameters required for
            defect interaction calculations including interaction
            strength, range, and Green function parameters.
            Uses energy-based parameters instead of mass terms.
        """
        self.interaction_strength = self.params.get("interaction_strength", 1.0)
        self.interaction_range = self.params.get("interaction_range", 1.0)
        self.screening_length = self.params.get("screening_length", 0.5)
        self.cutoff_radius = self.params.get("cutoff_radius", 0.1)

        # Remove default screening (λ=0 as per ALL.md)
        self.tempered_lambda = self.params.get("tempered_lambda", 0.0)

        # Forbid mass terms: assert tempered_lambda==0 in base configs
        if self.tempered_lambda > 0:
            # Allow override only in diagnostic paths
            diagnostic_mode = self.params.get("diagnostic_mode", False)
            if not diagnostic_mode:
                raise ValueError(
                    f"Mass terms forbidden in base regime: tempered_lambda={self.tempered_lambda} > 0. Use diagnostic_mode=True for diagnostics only."
                )

    def compute_interaction_forces(
        self, positions: List[np.ndarray], charges: List[int]
    ) -> List[np.ndarray]:
        """
        Compute interaction forces between defects.

        Physical Meaning:
            Calculates the forces acting on each defect due to
            interactions with all other defects in the system.

        Mathematical Foundation:
            Fᵢ = -∇ᵢ Σⱼ qᵢqⱼ G(rᵢⱼ) where G is the Green function
            and the sum is over all other defects j ≠ i.

        Args:
            positions: List of defect positions
            charges: List of defect charges

        Returns:
            List of force vectors for each defect
        """
        return self.forces_computation.compute_interaction_forces(positions, charges)
    
    def compute_interaction_potential(
        self, positions: List[np.ndarray], charges: List[int]
    ) -> float:
        """
        Compute total interaction potential energy.

        Physical Meaning:
            Calculates the total potential energy of the defect
            system due to all pairwise interactions.

        Mathematical Foundation:
            U = (1/2) Σᵢⱼ qᵢqⱼ G(rᵢⱼ) where the factor 1/2 avoids
            double counting.

        Args:
            positions: List of defect positions
            charges: List of defect charges

        Returns:
            Total interaction potential energy
        """
        return self.forces_computation.compute_interaction_potential(positions, charges)
    
    def simulate_defect_annihilation(
        self, defect_pair: List[int], positions: List[np.ndarray], charges: List[int]
    ) -> Dict[str, Any]:
        """
        Simulate annihilation of defect-antidefect pair.

        Physical Meaning:
            Models the process where a defect and antidefect approach
            and annihilate, releasing energy and creating topological
            transitions in the field.

        Mathematical Foundation:
            Annihilation occurs when defects of opposite charge
            approach within a critical distance, leading to
            energy release and field relaxation.

        Args:
            defect_pair: Indices of defect and antidefect
            positions: Current defect positions
            charges: Current defect charges

        Returns:
            Dictionary containing annihilation results
        """
        return self.energy_computation.simulate_defect_annihilation(
            defect_pair, positions, charges
        )
