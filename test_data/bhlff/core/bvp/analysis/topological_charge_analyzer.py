"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological charge analyzer for BVP framework.

This module implements comprehensive topological charge analysis for the
7D BVP field, including winding number computation, defect identification,
and topological characterization according to the theoretical framework.
"""

import numpy as np
from typing import Dict, Any, Tuple, List, Optional
from scipy.ndimage import label, center_of_mass

# CUDA optimization imports
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = np

from ...domain import Domain
from ..bvp_constants import BVPConstants
from ..memory_decorator import memory_protected_class_method
from .defect_analyzer import TopologicalDefectAnalyzer
from .charge_computation import ChargeComputation
from .phase_analysis import PhaseAnalysis


class TopologicalChargeAnalyzer:
    """
    Analyzer for topological charge in BVP field.

    Physical Meaning:
        Computes the topological charge of the BVP field,
        identifying topological defects and their properties
        according to the theoretical framework.

    Mathematical Foundation:
        Implements topological charge analysis with proper winding
        number computation and defect characterization for 7D phase field theory.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ):
        """
        Initialize topological charge analyzer.

        Physical Meaning:
            Sets up the topological charge analyzer with the computational domain
            and configuration parameters for analyzing topological defects
            in the BVP field.

        Args:
            domain (Domain): Computational domain for analysis.
            config (Dict[str, Any]): Analysis configuration including:
                - charge_threshold: Threshold for significant charge
                - defect_size: Minimum size for defect detection
                - winding_precision: Precision for winding number computation
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants or BVPConstants(config)
        self._setup_analysis_parameters()

    def _setup_analysis_parameters(self) -> None:
        """
        Setup analysis parameters.

        Physical Meaning:
            Initializes parameters for topological charge analysis based on
            the domain properties and configuration.
        """
        # Topological analysis parameters
        self.charge_threshold = self.config.get("charge_threshold", 0.1)
        self.winding_precision = self.config.get("winding_precision", 1e-6)

        # Analysis precision
        self.min_charge = self.config.get("min_charge", 0.01)
        self.max_charge = self.config.get("max_charge", 10.0)
        self.stability_threshold = self.config.get("stability_threshold", 0.8)

        # Initialize analyzers
        self.defect_analyzer = TopologicalDefectAnalyzer(
            self.domain, self.config, self.constants
        )
        self.charge_computation = ChargeComputation(
            self.domain, self.config, self.constants
        )
        self.phase_analysis = PhaseAnalysis(self.domain, self.config, self.constants)

    def compute_topological_charge(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Compute topological charge using block processing and vectorization.

        Physical Meaning:
            Computes the topological charge using block processing to handle
            large domains efficiently with CUDA acceleration and vectorization.

        Mathematical Foundation:
            Q = (1/2π) ∮ ∇φ · dl computed in blocks with vectorized operations
            for maximum performance on large 7D domains.

        Args:
            field (np.ndarray): BVP field for analysis.

        Returns:
            Dict[str, Any]: Analysis results including:
                - topological_charge: Total topological charge
                - charge_locations: List of charge locations
                - charge_stability: Stability measure of charges
                - defect_analysis: Detailed defect analysis
        """
        # Convert to complex field for phase analysis
        if np.iscomplexobj(field):
            complex_field = field
        else:
            complex_field = field.astype(complex)

        # Compute phase field with vectorization
        phase = np.angle(complex_field)

        # Process in blocks to handle large domains
        all_defects = []
        all_charges = []
        all_charge_locations = []

        # Block processing for large domains
        block_size = self.config.get("block_size", 64)
        for block_start in range(0, phase.shape[0], block_size):
            block_end = min(block_start + block_size, phase.shape[0])
            block_phase = phase[block_start:block_end]

            # Compute topological charge for this block
            block_charges = self.charge_computation.compute_block_charge(block_phase)
            all_charges.extend(block_charges)

            # Find charge locations in this block
            block_locations = self.charge_computation.find_charge_locations(
                block_phase, block_start
            )
            all_charge_locations.extend(block_locations)

            # Analyze defects in this block
            block_defects = self.defect_analyzer.analyze_block_defects(
                block_phase, block_start
            )
            all_defects.extend(block_defects)

        # Compute total topological charge
        total_charge = sum(all_charges)

        # Analyze charge stability
        charge_stability = self._analyze_charge_stability(all_charges)

        # Perform detailed defect analysis
        defect_analysis = self.defect_analyzer.analyze_defects(
            all_defects, all_charge_locations
        )

        return {
            "topological_charge": float(total_charge),
            "charge_locations": all_charge_locations,
            "charge_stability": charge_stability,
            "defect_analysis": defect_analysis,
            "total_defects": len(all_defects),
            "positive_charges": sum(1 for charge in all_charges if charge > 0),
            "negative_charges": sum(1 for charge in all_charges if charge < 0),
        }

    def analyze_defect_interactions(
        self, charge_locations: List[Tuple[int, ...]], charges: List[float]
    ) -> Dict[str, Any]:
        """
        Analyze interactions between topological defects.

        Physical Meaning:
            Analyzes the interactions between topological defects to understand
            their collective behavior and stability.

        Args:
            charge_locations (List[Tuple[int, ...]]): Locations of charges.
            charges (List[float]): Charge values.

        Returns:
            Dict[str, Any]: Defect interaction analysis.
        """
        defect_types = []
        defect_strengths = []
        defect_interactions = []

        for i, (location, charge) in enumerate(zip(charge_locations, charges)):
            # Classify defect type
            if abs(charge) > self.charge_threshold:
                defect_type = (
                    "strong" if abs(charge) > 2 * self.charge_threshold else "weak"
                )
            else:
                defect_type = "weak"

            defect_types.append(defect_type)
            defect_strengths.append(abs(charge))

            # Analyze interactions with other defects
            for j, (other_location, other_charge) in enumerate(
                zip(charge_locations, charges)
            ):
                if i != j:
                    # Calculate distance between defects
                    distance = np.sqrt(
                        sum((a - b) ** 2 for a, b in zip(location, other_location))
                    )

                    # Calculate interaction strength
                    interaction_strength = (charge * other_charge) / (
                        distance**2 + 1e-10
                    )

                    # Determine interaction type
                    if charge * other_charge > 0:
                        interaction_type = "repulsive"
                    else:
                        interaction_type = "attractive"

                    interaction = {
                        "defect_pair": (i, j),
                        "distance": float(distance),
                        "interaction_strength": float(interaction_strength),
                        "interaction_type": interaction_type,
                    }
                    defect_interactions.append(interaction)

        return {
            "defect_count": len(charge_locations),
            "defect_types": defect_types,
            "defect_strengths": defect_strengths,
            "defect_interactions": defect_interactions,
            "total_positive_charge": sum(charge for charge in charges if charge > 0),
            "total_negative_charge": sum(charge for charge in charges if charge < 0),
        }

    def analyze_phase_structure(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Analyze phase structure of the field.

        Physical Meaning:
            Analyzes the phase structure of the BVP field to understand
            the topological characteristics and phase coherence.

        Args:
            field (np.ndarray): BVP field for analysis.

        Returns:
            Dict[str, Any]: Phase structure analysis.
        """
        return self.phase_analysis.analyze_phase_structure(field)

    def get_analysis_parameters(self) -> Dict[str, Any]:
        """
        Get current analysis parameters.

        Physical Meaning:
            Returns the current parameters used for topological charge analysis.

        Returns:
            Dict[str, Any]: Analysis parameters.
        """
        return {
            "charge_threshold": self.charge_threshold,
            "defect_size": self.defect_size,
            "winding_precision": self.winding_precision,
            "min_charge": self.min_charge,
            "max_charge": self.max_charge,
            "stability_threshold": self.stability_threshold,
        }

    def _analyze_charge_stability(self, charges: List[float]) -> float:
        """Analyze stability of topological charges."""
        if not charges:
            return 0.0

        # Calculate charge variance as stability measure
        charge_variance = np.var(charges)
        charge_mean = np.mean(np.abs(charges))

        # Normalize stability measure
        stability = 1.0 / (1.0 + charge_variance / (charge_mean**2 + 1e-10))
        return float(stability)
