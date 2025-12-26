"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological defect analyzer for BVP framework.

This module implements analysis of topological defects in the
7D BVP field, including defect identification, classification,
and interaction analysis according to the theoretical framework.

Physical Meaning:
    Analyzes topological defects in the BVP field, identifying
    their types, strengths, and interactions according to the
    theoretical framework.

Mathematical Foundation:
    Implements topological defect analysis with proper defect
    identification and characterization for 7D phase field theory.

Example:
    >>> analyzer = TopologicalDefectAnalyzer(domain, config)
    >>> defects = analyzer.find_topological_defects(phase_field)
    >>> print(f"Found {len(defects)} defects")
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

from ..domain import Domain
from .bvp_constants import BVPConstants
from .memory_decorator import memory_protected_class_method


class TopologicalDefectAnalyzer:
    """
    Analyzer for topological defects in BVP field.

    Physical Meaning:
        Identifies and analyzes topological defects in the BVP field,
        including their types, positions, and interactions.

    Mathematical Foundation:
        Implements topological defect analysis with proper defect
        identification and characterization for 7D phase field theory.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ):
        """
        Initialize topological defect analyzer.

        Physical Meaning:
            Sets up the defect analyzer with the computational domain
            and configuration parameters for analyzing topological defects
            in the BVP field.

        Args:
            domain (Domain): Computational domain for analysis.
            config (Dict[str, Any]): Analysis configuration including:
                - defect_size: Minimum size for defect detection
                - gradient_threshold: Threshold for defect identification
                - interaction_radius: Radius for defect interaction analysis
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
            Initializes parameters for topological defect analysis based on
            the domain properties and configuration.
        """
        # Defect analysis parameters
        self.defect_size = self.config.get("defect_size", 3)
        self.gradient_threshold = self.config.get("gradient_threshold", 0.5)
        self.interaction_radius = self.config.get("interaction_radius", 5.0)

        # Analysis precision
        self.min_defect_strength = self.config.get("min_defect_strength", 0.1)
        self.max_defect_strength = self.config.get("max_defect_strength", 10.0)
        self.stability_threshold = self.config.get("stability_threshold", 0.8)

    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="phase", dtype_param="phase"
    )
    def find_topological_defects(self, phase: np.ndarray) -> List[Tuple[int, ...]]:
        """
        Find topological defects in the phase field with CUDA optimization.

        Physical Meaning:
            Identifies points where the phase field has singularities
            or rapid changes, indicating topological defects.

        Mathematical Foundation:
            Defects are identified by analyzing phase gradients
            and looking for points where the phase changes rapidly.

        Args:
            phase (np.ndarray): Phase field.

        Returns:
            List[Tuple[int, ...]]: List of defect locations.
        """
        # Use CUDA if available
        if CUDA_AVAILABLE:
            return self._find_topological_defects_cuda(phase)
        else:
            return self._find_topological_defects_cpu(phase)

    def _find_topological_defects_cuda(
        self, phase: np.ndarray
    ) -> List[Tuple[int, ...]]:
        """
        Find topological defects using CUDA acceleration.

        Physical Meaning:
            CUDA-accelerated identification of topological defects
            using vectorized gradient computation on GPU.
        """
        try:
            # Move data to GPU
            phase_gpu = cp.asarray(phase)

            # Compute phase gradients using CUDA
            gradients = []
            for i in range(phase_gpu.ndim):
                grad = cp.gradient(phase_gpu, axis=i)
                gradients.append(grad)

            # Compute gradient magnitude using CUDA
            grad_magnitude = cp.sqrt(sum(grad**2 for grad in gradients))

            # Find high gradient regions using CUDA
            high_grad_threshold = cp.percentile(grad_magnitude, 95)
            high_grad_mask = grad_magnitude > high_grad_threshold

            # Move back to CPU for scipy operations
            high_grad_mask_cpu = cp.asnumpy(high_grad_mask)

            # Find connected components of high gradient regions
            labeled_mask, num_components = label(high_grad_mask_cpu)

            defects = []
            for i in range(1, num_components + 1):
                component_mask = labeled_mask == i
                if np.sum(component_mask) >= self.defect_size:
                    # Find center of mass of the component
                    center = center_of_mass(component_mask)
                    # Convert to integer coordinates
                    center_int = tuple(int(round(c)) for c in center)
                    defects.append(center_int)

            return defects

        except Exception:
            # Fallback to CPU if CUDA fails
            return self._find_topological_defects_cpu(phase)

    def _find_topological_defects_cpu(self, phase: np.ndarray) -> List[Tuple[int, ...]]:
        """
        Find topological defects using CPU with vectorized operations.

        Physical Meaning:
            CPU-optimized identification of topological defects
            using vectorized NumPy operations.
        """
        # Compute phase gradients using vectorized operations
        gradients = []
        for i in range(phase.ndim):
            grad = np.gradient(phase, axis=i)
            gradients.append(grad)

        # Compute gradient magnitude using vectorized operations
        grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients))

        # Find high gradient regions using vectorized operations
        high_grad_threshold = np.percentile(grad_magnitude, 95)
        high_grad_mask = grad_magnitude > high_grad_threshold

        # Find connected components of high gradient regions
        labeled_mask, num_components = label(high_grad_mask)

        defects = []
        for i in range(1, num_components + 1):
            component_mask = labeled_mask == i
            if np.sum(component_mask) >= self.defect_size:
                # Find center of mass of the component
                center = center_of_mass(component_mask)
                # Convert to integer coordinates
                center_int = tuple(int(round(c)) for c in center)
                defects.append(center_int)

        return defects

    def analyze_defect_types(
        self, phase: np.ndarray, defect_locations: List[Tuple[int, ...]]
    ) -> List[str]:
        """
        Analyze types of topological defects.

        Physical Meaning:
            Classifies topological defects based on their local
            phase structure and gradient patterns.

        Mathematical Foundation:
            Defect types are determined by analyzing the local
            phase structure around each defect.

        Args:
            phase (np.ndarray): Phase field.
            defect_locations (List[Tuple[int, ...]]): Defect locations.

        Returns:
            List[str]: List of defect types.
        """
        defect_types = []

        for location in defect_locations:
            # Extract neighborhood around defect
            neighborhood = self._extract_neighborhood(phase, location, radius=2)

            # Analyze local phase structure
            phase_variance = np.var(neighborhood)
            phase_gradient = np.mean(np.abs(np.gradient(neighborhood)))

            # Classify defect type based on local properties
            if phase_variance > 1.0 and phase_gradient > 0.5:
                defect_types.append("vortex")
            elif phase_variance > 0.5:
                defect_types.append("dislocation")
            else:
                defect_types.append("weak_defect")

        return defect_types

    def analyze_defect_interactions(
        self, defect_locations: List[Tuple[int, ...]], defect_charges: List[float]
    ) -> Dict[str, Any]:
        """
        Analyze interactions between topological defects.

        Physical Meaning:
            Computes interaction strengths between topological defects
            based on their charges and spatial separation.

        Mathematical Foundation:
            Defect interactions are computed using fractional Green functions
            G_β(r) ∝ r^(2β-3) for fractional Laplacian (-Δ)^β. For β=1,
            this reduces to classical Coulomb interactions.

        Args:
            defect_locations (List[Tuple[int, ...]]): Defect locations.
            defect_charges (List[float]): Defect charges.

        Returns:
            Dict[str, Any]: Interaction analysis results.
        """
        if len(defect_locations) < 2:
            return {
                "interaction_energy": 0.0,
                "attractive_pairs": 0,
                "repulsive_pairs": 0,
                "interaction_strength": 0.0,
            }

        interactions = []
        attractive_pairs = 0
        repulsive_pairs = 0

        for i in range(len(defect_locations)):
            for j in range(i + 1, len(defect_locations)):
                # Compute distance between defects
                dist = np.sqrt(
                    sum(
                        (a - b) ** 2
                        for a, b in zip(defect_locations[i], defect_locations[j])
                    )
                )

                # Compute interaction strength using fractional Green function
                # For fractional Laplacian: interaction ∝ q₁q₂ G_β(r) where G_β(r) ∝ r^(2β-3)
                beta = self.config.get("beta", 1.0)
                # Always use fractional Green function: G_β(r) ∝ r^(2β-3)
                power = 2 * beta - 3
                green_value = (dist + 1e-6) ** power

                interaction = defect_charges[i] * defect_charges[j] * green_value
                interactions.append(interaction)

                # Classify interaction type
                if interaction < 0:
                    attractive_pairs += 1
                elif interaction > 0:
                    repulsive_pairs += 1

        # Compute total interaction energy
        interaction_energy = sum(interactions)
        interaction_strength = np.mean(np.abs(interactions)) if interactions else 0.0

        return {
            "interaction_energy": float(interaction_energy),
            "attractive_pairs": attractive_pairs,
            "repulsive_pairs": repulsive_pairs,
            "interaction_strength": float(interaction_strength),
        }

    def _extract_neighborhood(
        self, field: np.ndarray, center: Tuple[int, ...], radius: int
    ) -> np.ndarray:
        """
        Extract neighborhood around a point.

        Physical Meaning:
            Extracts a small neighborhood around a point for
            local analysis of field properties.

        Args:
            field (np.ndarray): Field to extract from.
            center (Tuple[int, ...]): Center point.
            radius (int): Neighborhood radius.

        Returns:
            np.ndarray: Extracted neighborhood.
        """
        slices = []
        for i, coord in enumerate(center):
            start = max(0, coord - radius)
            end = min(field.shape[i], coord + radius + 1)
            slices.append(slice(start, end))

        return field[tuple(slices)]

    def get_analysis_parameters(self) -> Dict[str, Any]:
        """
        Get current analysis parameters.

        Physical Meaning:
            Returns the current parameters used for topological defect analysis.

        Returns:
            Dict[str, Any]: Analysis parameters.
        """
        return {
            "defect_size": self.defect_size,
            "gradient_threshold": self.gradient_threshold,
            "interaction_radius": self.interaction_radius,
            "min_defect_strength": self.min_defect_strength,
            "max_defect_strength": self.max_defect_strength,
            "stability_threshold": self.stability_threshold,
        }
